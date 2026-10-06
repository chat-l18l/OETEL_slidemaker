import shutil
import subprocess
from pathlib import Path

import pytest

from slidesmith import tts, video
from slidesmith.parser import Diagnostics
from slidesmith.project import load_course

from test_build import make_course
from test_pdf import needs_browser


def test_lexicon_and_sentence_ranges():
    seg = tts.make_segment("s", 1, "De *ESP32* start. Klaar!", "", {"ESP32": "E S P tweeëndertig"}, None)
    assert seg.text == "De ESP32 start. Klaar!"
    assert seg.spoken == "De E S P tweeëndertig start. Klaar!"
    (s1, a1, b1), (s2, a2, b2) = seg.sentences
    assert (s1, seg.spoken[a1:b1]) == ("De ESP32 start.", "De E S P tweeëndertig start.")
    assert seg.spoken[a2:b2] == "Klaar!"


def test_lexicon_matches_whole_words_only():
    assert tts.apply_lexicon("USB en USBC", {"USB": "U S B"}) == "U S B en USBC"


def test_segment_key_depends_on_voice_and_text():
    cfg = tts.DEFAULT_TTS
    a = tts.make_segment("s", 0, "Hallo.", "", {}, None)
    b = tts.make_segment("s", 0, "Hallo!", "", {}, None)
    assert tts.segment_key(a, "v1", cfg) != tts.segment_key(b, "v1", cfg)
    assert tts.segment_key(a, "v1", cfg) != tts.segment_key(a, "v2", cfg)
    assert tts.segment_key(a, "v1", cfg) == tts.segment_key(a, "v1", cfg)


def test_wrap_balances_and_limits_lines():
    text = "Vandaag kijken we hoe je je elektronica-werkbank verandert in een geautomatiseerd testlab."
    cues = video._wrap(text)
    assert " ".join(c.replace("\n", " ") for c in cues) == text
    assert all(len(line) <= video.SUB_LINE + 6 for c in cues for line in c.split("\n"))
    assert all(c.count("\n") <= 1 for c in cues)


def test_timeline_uses_audio_durations():
    deck = {"slides": [{"id": "a", "chapter": 0, "steps": [5.0, 2.0]},
                       {"id": "b", "chapter": 1, "steps": [5.0]}],
            "chapters": [{"title": "A"}, {"title": "B"}]}
    clip = tts.Clip(Path("x.mp3"), 2.5, [], [], [])
    tl = video.make_timeline(deck, {(0, 1): (None, clip)}, {"lead": 0.3, "tail": 0.6})
    assert [round(s.dur, 2) for s in tl.steps] == [5.0, 3.4, 5.0]
    assert tl.chapters == [{"title": "A", "start": 0.0, "dur": 8.4}, {"title": "B", "start": 8.4, "dur": 5.0}]
    assert round(tl.steps[1].speech_start, 2) == 5.3


def test_subtitles_never_overlap(tmp_path):
    cues = [(0.0, 0.2, "Hoi"), (0.5, 2.0, "Daarna")]
    video.write_subtitles(cues, tmp_path / "a.srt", tmp_path / "a.vtt")
    srt = (tmp_path / "a.srt").read_text()
    assert "00:00:00,000 --> 00:00:00,499" in srt
    assert (tmp_path / "a.vtt").read_text().startswith("WEBVTT")


@needs_browser
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="geen ffmpeg")
def test_silent_video(tmp_path):
    root = make_course(tmp_path / "cursus")
    diag = Diagnostics()
    course = load_course(root, diag)
    lesson = course.lessons[0]
    out = tmp_path / "b"
    written = video.build_lesson_video(course, lesson, "nl", out, diag, confirm=lambda *a: False,
                                       silent=True)
    mp4 = out / "video/nl/01-les.mp4"
    assert mp4 in written
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(mp4)], capture_output=True, text=True).stdout)
    timeline = (out / ".cache/video/01-les-nl/timeline.json").read_text()
    assert abs(dur - __import__("json").loads(timeline)["total"]) < 0.5
    assert (out / "video/nl/01-les-chapters.txt").read_text().startswith("00:00 Hoofdstuk A")
    assert "Een." in (out / "video/nl/01-les.nl.srt").read_text()
