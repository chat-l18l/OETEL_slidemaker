"""Text-to-speech for script fragments, with a content-addressed cache.

Each script fragment (one reveal step) becomes one clip. A clip is cached under a hash
of everything that influences the audio, so editing one slide only re-synthesizes the
fragments that changed. Clips keep the provider's per-character timing, which the
subtitles use.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import secrets
from .model import Course, Loc
from .parser import SourceError

API = "https://api.elevenlabs.io"
DEFAULT_TTS = {
    "provider": "elevenlabs",
    "model": "eleven_multilingual_v2",
    # premade "George" until the course author's own cloned voice is configured
    "voice": {"nl": "JBFqnCBsd6RMkjVDRZzb", "en": "JBFqnCBsd6RMkjVDRZzb"},
    "settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0},
}


@dataclass
class Segment:
    """One script fragment to be spoken."""

    slide_id: str
    step: int
    text: str  # as written (subtitles)
    spoken: str  # after the pronunciation lexicon
    previous: str  # previous fragment of the same slide (prosody context)
    loc: Loc | None
    key: str = ""
    # sentence ranges: (display sentence, start, end) as character offsets into `spoken`
    sentences: list[tuple[str, int, int]] = field(default_factory=list)


@dataclass
class Clip:
    audio: Path
    duration: float
    chars: list[str]
    starts: list[float]
    ends: list[float]


def tts_config(course: Course) -> dict:
    raw = course.config.get("tts") or {}
    cfg = {**DEFAULT_TTS, **raw}
    cfg["voice"] = {**DEFAULT_TTS["voice"], **(raw.get("voice") or {})}
    cfg["settings"] = {**DEFAULT_TTS["settings"], **(raw.get("settings") or {})}
    return cfg


def load_lexicon(course: Course) -> dict[str, dict[str, str]]:
    """lexicon.yaml in the course root: {lang: {term: how it is spoken}}."""
    path = course.root / "lexicon.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(lang): {str(k): str(v) for k, v in (terms or {}).items()} for lang, terms in data.items()}


def apply_lexicon(text: str, terms: dict[str, str]) -> str:
    for term in sorted(terms, key=len, reverse=True):
        text = re.sub(rf"(?<!\w){re.escape(term)}(?!\w)", terms[term], text)
    return text


_SENTENCE_RE = re.compile(r"[^.!?…]+(?:[.!?…]+[\"')\]]*|$)\s*")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_RE.findall(" ".join(text.split())) if s.strip()]


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links
    text = re.sub(r"[*_`]", "", text)
    return " ".join(text.split())


def make_segment(slide_id: str, step: int, raw: str, previous: str, terms: dict[str, str],
                 loc: Loc | None) -> Segment:
    text = strip_markdown(raw)
    spoken_parts, sentences, pos = [], [], 0
    for sentence in split_sentences(text):
        spoken = apply_lexicon(sentence, terms)
        if spoken_parts:
            pos += 1  # joining space
        sentences.append((sentence, pos, pos + len(spoken)))
        spoken_parts.append(spoken)
        pos += len(spoken)
    return Segment(slide_id, step, text, " ".join(spoken_parts), previous, loc, sentences=sentences)


def segment_key(seg: Segment, voice: str, cfg: dict) -> str:
    payload = json.dumps([cfg["provider"], cfg["model"], voice, cfg["settings"], seg.spoken, seg.previous],
                         sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()[:20]


class Cache:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def paths(self, key: str) -> tuple[Path, Path]:
        return self.root / f"{key}.mp3", self.root / f"{key}.json"

    def get(self, key: str) -> Clip | None:
        audio, meta = self.paths(key)
        if not (audio.exists() and meta.exists()):
            return None
        m = json.loads(meta.read_text(encoding="utf-8"))
        return Clip(audio, m["duration"], m["chars"], m["starts"], m["ends"])

    def put(self, key: str, audio_bytes: bytes, alignment: dict, info: dict) -> Clip:
        audio, meta = self.paths(key)
        audio.write_bytes(audio_bytes)
        duration = probe_duration(audio)
        m = {"duration": duration, "chars": alignment["characters"],
             "starts": alignment["character_start_times_seconds"],
             "ends": alignment["character_end_times_seconds"], **info}
        meta.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
        return Clip(audio, duration, m["chars"], m["starts"], m["ends"])


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                        str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        raise SourceError(f"ffprobe kon {path} niet lezen: {r.stderr.strip()}")
    return float(r.stdout.strip())


class ElevenLabs:
    def __init__(self) -> None:
        self.key = secrets.get("ELEVENLABS_API_KEY")
        if not self.key:
            raise SourceError("ELEVENLABS_API_KEY ontbreekt (omgeving of ~/.config/slidesmith/secrets.env)")

    def _request(self, method: str, path: str, body: dict | None = None) -> tuple[dict, dict]:
        req = urllib.request.Request(
            API + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"xi-api-key": self.key, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read()), dict(r.headers)
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read()).get("detail")
            except Exception:
                detail = e.reason
            msg = detail.get("message") if isinstance(detail, dict) else detail
            raise SourceError(f"ElevenLabs {e.code}: {msg}") from None

    def quota(self) -> tuple[int, int] | None:
        """(used, limit) characters, or None if the key may not read it."""
        try:
            d, _ = self._request("GET", "/v1/user/subscription")
            return d["character_count"], d["character_limit"]
        except SourceError:
            return None

    def synthesize(self, seg: Segment, voice: str, cfg: dict) -> tuple[bytes, dict, int]:
        body = {"text": seg.spoken, "model_id": cfg["model"], "voice_settings": cfg["settings"]}
        if seg.previous:
            body["previous_text"] = seg.previous
        d, headers = self._request(
            "POST", f"/v1/text-to-speech/{voice}/with-timestamps?output_format=mp3_44100_128", body)
        cost = int(headers.get("character-cost") or headers.get("Character-Cost") or len(seg.spoken))
        return base64.b64decode(d["audio_base64"]), d["alignment"], cost


def provider(cfg: dict):
    if cfg["provider"] != "elevenlabs":
        raise SourceError(f"onbekende TTS-provider '{cfg['provider']}' (alleen elevenlabs)")
    return ElevenLabs()


def segments_for(course: Course, slides, lang: str) -> list[Segment]:
    """All non-empty script fragments of the given slides, in order."""
    terms = load_lexicon(course).get(lang, {})
    out = []
    for s in slides:
        b = s.block(lang)
        previous = ""
        for step, raw in enumerate(b.script):
            if not raw.strip():
                continue
            seg = make_segment(s.id, step, raw, previous, terms, b.loc)
            out.append(seg)
            previous = seg.spoken
    return out
