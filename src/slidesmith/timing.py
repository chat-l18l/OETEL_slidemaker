"""Duration estimates per reveal step, used for the time bar (and later for video)."""

from __future__ import annotations

import re

MIN_STEP = 1.5  # seconds
NO_SCRIPT_SLIDE = 5.0
NO_SCRIPT_STEP = 2.0
_WORD_RE = re.compile(r"\w+", re.UNICODE)


def words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def step_durations(script: list[str], steps: int, wpm: float) -> list[float]:
    """Seconds for step 0 (slide appears) .. step `steps`."""
    if not any(s.strip() for s in script):
        return [NO_SCRIPT_SLIDE] + [NO_SCRIPT_STEP] * steps
    segs = list(script) + [""] * (steps + 1 - len(script))
    # more script segments than steps: fold the excess into the last step
    if len(segs) > steps + 1:
        segs = segs[:steps] + [" ".join(segs[steps:])]
    return [max(MIN_STEP, words(s) / wpm * 60) for s in segs]
