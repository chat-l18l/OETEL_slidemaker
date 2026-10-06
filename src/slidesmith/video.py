"""Concept video: one frame per reveal step, TTS audio per script fragment, assembled by ffmpeg.

Timeline per step = lead + spoken audio + tail (or the estimate when there is no audio).
The chapter time bar is drawn by ffmpeg so it moves smoothly instead of jumping per step.
"""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
import sys
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from . import browser, tts
from .build import Assets, build_lesson, copy_static
from .model import Course, Lesson
from .parser import Diagnostics, SourceError

SAMPLE_RATE = 44100
DEFAULT_VIDEO = {"fps": 30, "lead": 0.3, "tail": 0.6, "crf": 20, "preset": "veryfast"}
SUB_LINE = 42  # characters per subtitle line, two lines per cue


@dataclass
class Step:
    h: int
    k: int
    slide_id: str
    chapter: int
    start: float = 0.0
    dur: float = 0.0
    frame: Path | None = None
    seg: tts.Segment | None = None
    clip: tts.Clip | None = None
    speech_start: float = 0.0


@dataclass
class Timeline:
    steps: list[Step] = field(default_factory=list)
    chapters: list[dict] = field(default_factory=list)  # title, start, dur
    total: float = 0.0


def video_config(course: Course) -> dict:
    return {**DEFAULT_VIDEO, **(course.config.get("video") or {})}


# ---------------------------------------------------------------- TTS

def synthesize(course: Course, lesson: Lesson, lang: str, cache: tts.Cache,
               confirm: Callable[[int, tuple[int, int] | None], bool]) -> dict[tuple[int, int], tuple]:
    """Make sure every script fragment has audio. Returns {(h, step): (segment, clip)}."""
    cfg = tts.tts_config(course)
    voice = cfg["voice"].get(lang)
    if not voice:
        raise SourceError(f"geen TTS-stem ingesteld voor taal '{lang}' (course.yaml: tts.voice.{lang})")
    slides = [s for ch in lesson.chapters for s in ch.slides]
    todo, result = [], {}
    for h, s in enumerate(slides):
        for seg in tts.segments_for(course, [s], lang):
            seg.key = tts.segment_key(seg, voice, cfg)
            clip = cache.get(seg.key)
            result[(h, seg.step)] = (seg, clip)
            if clip is None:
                todo.append((h, seg))
    if todo:
        chars = sum(len(seg.spoken) for _, seg in todo)
        prov = tts.provider(cfg)
        if not confirm(chars, prov.quota()):
            raise SourceError("gestopt: geen toestemming voor TTS-synthese")

        def work(item):
            h, seg = item
            audio, alignment, cost = prov.synthesize(seg, voice, cfg)
            info = {"text": seg.text, "spoken": seg.spoken, "voice": voice, "model": cfg["model"], "cost": cost}
            return h, seg, cache.put(seg.key, audio, alignment, info)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            for n, (h, seg, clip) in enumerate(pool.map(work, todo), 1):
                result[(h, seg.step)] = (seg, clip)
                print(f"  tts {n}/{len(todo)}: {seg.slide_id} stap {seg.step}", file=sys.stderr)
    return result


# ---------------------------------------------------------------- timeline + frames

def make_timeline(deck: dict, audio: dict, vcfg: dict) -> Timeline:
    tl = Timeline()
    t = 0.0
    for h, info in enumerate(deck["slides"]):
        for k, estimate in enumerate(info["steps"]):
            st = Step(h=h, k=k, slide_id=info["id"], chapter=info["chapter"], start=t)
            seg, clip = audio.get((h, k), (None, None))
            if clip is not None:
                st.seg, st.clip = seg, clip
                st.speech_start = t + vcfg["lead"]
                st.dur = vcfg["lead"] + clip.duration + vcfg["tail"]
            else:
                st.dur = estimate
            t += st.dur
            tl.steps.append(st)
    tl.total = t
    for ci, ch in enumerate(deck["chapters"]):
        own = [s for s in tl.steps if s.chapter == ci]
        start = own[0].start if own else 0.0
        tl.chapters.append({"title": ch["title"], "start": start,
                            "dur": sum(s.dur for s in own)})
    return tl


def capture_frames(page_path: Path, frames: Path) -> tuple[dict, Callable[[Timeline], None]]:
    """Open the deck in video mode; returns the deck data and a function that shoots all frames."""
    page = browser.get().new_page(1920, 1080)
    page.goto(page_path.as_uri() + "?video")
    page.wait_for_function("window.Reveal && Reveal.isReady()", timeout=60_000)
    page.evaluate("document.fonts.ready")
    deck = page.evaluate("window.DECK")

    def shoot(tl: Timeline) -> None:
        frames.mkdir(parents=True, exist_ok=True)
        try:
            for st in tl.steps:
                page.evaluate(f"Reveal.slide({st.h}, 0, {st.k - 1})")
                page.wait_for_timeout(60)
                st.frame = frames / f"f{st.h:03d}_{st.k:02d}.png"
                page.screenshot(path=str(st.frame))
        finally:
            page.close()

    return deck, shoot


# ---------------------------------------------------------------- audio

def _pcm(path: Path) -> bytes:
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1",
                        "-ar", str(SAMPLE_RATE), "-"], capture_output=True)
    if r.returncode != 0:
        raise SourceError(f"ffmpeg kon {path} niet decoderen: {r.stderr.decode()[:200]}")
    return r.stdout


def build_audio(tl: Timeline, target: Path) -> None:
    total = int(round(tl.total * SAMPLE_RATE)) * 2
    buf = bytearray(total)
    for st in tl.steps:
        if st.clip is None:
            continue
        pcm = _pcm(st.clip.audio)
        at = int(round(st.speech_start * SAMPLE_RATE)) * 2
        end = min(total, at + len(pcm))
        buf[at:end] = pcm[: end - at]
    with wave.open(str(target), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(buf))


# ---------------------------------------------------------------- video

TIMEBAR_TRACK = "0x4b4d4f"  # the CSS bar's white@0.2 over the dark background, made opaque


def timebar_graph(tl: Timeline, accent: str, fps: int, src: str = "[0:v]") -> tuple[str, str]:
    """filter_complex for the chapter bar. drawbox evaluates its size only once, so the
    fill is an accent strip that `overlay` (evaluated per frame) slides into each segment.
    Returns (graph, output label)."""
    width, height, gap, pad = 1920, 9, 4, 2
    y = 1080 - height
    n = len(tl.chapters)
    avail = width - 2 * pad - gap * (n - 1)
    color = "0x" + accent.lstrip("#")
    d = f"{tl.total + 1:.3f}"
    chains, label, x = [f"{src}fps={fps}[v0]"], "v0", float(pad)
    for i, ch in enumerate(tl.chapters):
        w = max(2, round(avail * ch["dur"] / tl.total))
        dur = max(ch["dur"], 0.001)
        chains.append(f"color=c={TIMEBAR_TRACK}:s={w}x{height}:r={fps}:d={d}[t{i}]")
        chains.append(f"color=c={color}:s={w}x{height}:r={fps}:d={d}[a{i}]")
        chains.append(f"[t{i}][a{i}]overlay=x='-{w}+clip((t-{ch['start']:.3f})/{dur:.3f},0,1)*{w}'"
                      f":y=0:eval=frame:shortest=1[p{i}]")
        chains.append(f"[{label}][p{i}]overlay=x={round(x)}:y={y}:shortest=1[v{i + 1}]")
        label = f"v{i + 1}"
        x += w + gap
    return ";".join(chains), label


def encode(tl: Timeline, audio: Path, target: Path, vcfg: dict, accent: str, work: Path,
           timebar: bool) -> None:
    lst = work / "frames.txt"
    lines = []
    for st in tl.steps:
        lines += [f"file '{st.frame}'", f"duration {st.dur:.3f}"]
    lines.append(f"file '{tl.steps[-1].frame}'")  # concat demuxer needs the last frame twice
    lst.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if timebar and tl.chapters and tl.total > 0:
        graph, out = timebar_graph(tl, accent, vcfg["fps"])
    else:
        graph, out = f"[0:v]fps={vcfg['fps']}[v0]", "v0"
    graph += f";[{out}]format=yuv420p[vout]"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio),
           "-filter_complex", graph, "-map", "[vout]", "-map", "1:a", "-c:v", "libx264", "-preset", vcfg["preset"], "-tune", "stillimage",
           "-crf", str(vcfg["crf"]), "-c:a", "aac", "-b:a", "160k", "-t", f"{tl.total:.3f}",
           "-movflags", "+faststart", str(target)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SourceError("ffmpeg faalde:\n  " + "\n  ".join(r.stderr.strip().splitlines()[-6:]))


# ---------------------------------------------------------------- subtitles + chapters

def _ts(t: float, sep: str) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def _two_lines(words: list[str]) -> str:
    """Break a cue into at most two lines, as balanced as possible."""
    text = " ".join(words)
    if len(text) <= SUB_LINE:
        return text
    best = min(range(1, len(words)),
               key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]) + "\n" + " ".join(words[best:])


def _wrap(text: str) -> list[str]:
    """Split text into evenly sized cues of at most two lines of SUB_LINE characters."""
    words = text.split()
    if not words:
        return []
    n = -(-len(text) // int(2 * SUB_LINE * 0.9))  # number of cues, rounded up, with slack
    target = len(text) / n
    cues, cur = [], []
    for w in words:
        if cur and len(" ".join(cur + [w])) > target * 1.1 and len(cues) < n - 1:
            cues.append(cur)
            cur = []
        cur.append(w)
    cues.append(cur)
    return [_two_lines(c) for c in cues]


def _proportional(text: str, start: float, end: float) -> list[tuple[float, float, str]]:
    parts = [c for s in tts.split_sentences(text) for c in _wrap(s)]
    total = sum(len(p) for p in parts) or 1
    out, t = [], start
    for p in parts:
        d = (end - start) * len(p) / total
        out.append((t, t + d, p))
        t += d
    return out


def cues_spoken(tl: Timeline) -> list[tuple[float, float, str]]:
    """Cues for the spoken language, timed from the per-character alignment."""
    cues = []
    for st in tl.steps:
        if st.clip is None or st.seg is None:
            continue
        c = st.clip
        aligned = len(c.chars) == len(st.seg.spoken)
        for sentence, a, b in st.seg.sentences:
            chunks = _wrap(sentence)
            if not aligned:
                s0 = st.speech_start + c.duration * a / max(1, len(st.seg.spoken))
                s1 = st.speech_start + c.duration * b / max(1, len(st.seg.spoken))
                cues += _proportional(sentence, s0, s1)
                continue
            # spread the sentence's chunks over its aligned span, proportional to length
            s0 = st.speech_start + c.starts[a]
            s1 = st.speech_start + c.ends[max(a, b - 1)]
            total = sum(len(x) for x in chunks) or 1
            t = s0
            for x in chunks:
                d = (s1 - s0) * len(x) / total
                cues.append((t, t + d, x))
                t += d
    return cues


def cues_translated(tl: Timeline, lesson: Lesson, lang: str) -> list[tuple[float, float, str]]:
    """Cues in another language, spread over the speech intervals of the spoken version."""
    slides = [s for ch in lesson.chapters for s in ch.slides]
    cues = []
    for st in tl.steps:
        script = slides[st.h].block(lang).script
        if st.k >= len(script) or not script[st.k].strip():
            continue
        text = tts.strip_markdown(script[st.k])
        if st.clip is not None:
            s0, s1 = st.speech_start, st.speech_start + st.clip.duration
        else:
            s0, s1 = st.start, st.start + st.dur
        cues += _proportional(text, s0, s1)
    return cues


def write_subtitles(cues: list[tuple[float, float, str]], srt: Path, vtt: Path) -> None:
    srt_lines, vtt_lines = [], ["WEBVTT", ""]
    for i, (a, b, text) in enumerate(cues, 1):
        nxt = cues[i][0] if i < len(cues) else b + 0.8
        b = min(max(b, a + 0.8), max(b, nxt - 0.001))  # at least 0.8 s, never overlapping
        srt_lines += [str(i), f"{_ts(a, ',')} --> {_ts(b, ',')}", text, ""]
        vtt_lines += [f"{_ts(a, '.')} --> {_ts(b, '.')}", text, ""]
    srt.write_text("\n".join(srt_lines), encoding="utf-8")
    vtt.write_text("\n".join(vtt_lines), encoding="utf-8")


def youtube_chapters(tl: Timeline, diag: Diagnostics) -> str:
    def fmt(t: float) -> str:
        t = int(t)
        h, rest = divmod(t, 3600)
        m, s = divmod(rest, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

    lines = [f"{fmt(ch['start'])} {ch['title']}" for ch in tl.chapters]
    if len(tl.chapters) < 3:
        diag.warn(None, f"YouTube toont hoofdstukken pas vanaf 3 hoofdstukken (nu {len(tl.chapters)})")
    for ch in tl.chapters:
        if ch["dur"] < 10:
            diag.warn(None, f"hoofdstuk '{ch['title']}' is korter dan 10 s; YouTube negeert dan de hoofdstukken")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- main

def build_lesson_video(course: Course, lesson: Lesson, lang: str, out: Path, diag: Diagnostics,
                       confirm: Callable[[int, tuple[int, int] | None], bool], silent: bool = False,
                       sub_langs: list[str] | None = None) -> list[Path]:
    vcfg = video_config(course)
    copy_static(out)
    page = build_lesson(course, lesson, lang, out, Assets(out, diag), diag)
    work = out / ".cache" / "video" / f"{lesson.id}-{lang}"
    work.mkdir(parents=True, exist_ok=True)
    target_dir = out / "video" / lang
    target_dir.mkdir(parents=True, exist_ok=True)

    audio = {} if silent else synthesize(course, lesson, lang, tts.Cache(out / ".cache" / "tts"), confirm)
    deck, shoot = capture_frames(page, work / "frames")
    tl = make_timeline(deck, audio, vcfg)
    shoot(tl)

    wav = work / "audio.wav"
    build_audio(tl, wav)
    mp4 = target_dir / f"{lesson.id}.mp4"
    encode(tl, wav, mp4, vcfg, course.config["accent"], work, timebar=course.config["timebar"])
    written = [mp4]

    for sl in sub_langs if sub_langs is not None else course.langs:
        if sl == lang and not silent:
            cues = cues_spoken(tl)
        else:
            cues = cues_translated(tl, lesson, sl)
        srt, vtt = target_dir / f"{lesson.id}.{sl}.srt", target_dir / f"{lesson.id}.{sl}.vtt"
        write_subtitles(cues, srt, vtt)
        written += [srt, vtt]

    chapters = target_dir / f"{lesson.id}-chapters.txt"
    chapters.write_text(youtube_chapters(tl, diag), encoding="utf-8")
    written.append(chapters)
    (work / "timeline.json").write_text(json.dumps(
        {"total": tl.total, "chapters": tl.chapters,
         "steps": [{"slide": s.slide_id, "step": s.k, "start": round(s.start, 3), "dur": round(s.dur, 3)}
                   for s in tl.steps]}, indent=1, ensure_ascii=False), encoding="utf-8")
    return written
