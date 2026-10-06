"""Translation bookkeeping: marking translations as up to date with the NL source."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .model import Course, Loc, SOURCE_LANG
from .parser import question_hash, src_hash

_SRC_RE = re.compile(r"\ssrc=\S+")


def _set_src(line: str, lang: str, value: str) -> str:
    if _SRC_RE.search(line):
        return _SRC_RE.sub(f" src={value}", line, count=1)
    return re.sub(rf"^@{lang}\b", f"@{lang} src={value}", line, count=1)


def stamp(course: Course, lang: str, ids: set[str] | None = None) -> list[tuple[Loc, str]]:
    """Set `src=` of `lang` blocks to the current NL hash. Returns the changed locations."""
    edits: dict[Path, dict[int, str]] = defaultdict(dict)
    for lesson in course.lessons:
        for ch in lesson.chapters:
            for s in ch.slides:
                b = s.langs.get(lang)
                if b is None or SOURCE_LANG not in s.langs or (ids and s.id not in ids):
                    continue
                h = src_hash(s)
                if b.src != h:
                    edits[b.loc.file][b.loc.line] = h
            for q in ch.quizzes:
                for question in q.questions:
                    t = question.langs.get(lang)
                    if t is None or (ids and q.id not in ids):
                        continue
                    h = question_hash(question)
                    if t.src != h:
                        edits[t.loc.file][t.loc.line] = h
    changed = []
    for path, lines in edits.items():
        text = path.read_text(encoding="utf-8").split("\n")
        for lineno, h in lines.items():
            text[lineno - 1] = _set_src(text[lineno - 1], lang, h)
            changed.append((Loc(path, lineno), h))
        path.write_text("\n".join(text), encoding="utf-8")
    return changed
