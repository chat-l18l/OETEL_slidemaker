import pytest

from slidesmith import ai, review
from slidesmith.parser import Diagnostics
from slidesmith.project import load_course

CHAPTER = """---
title: Hoofdstuk
keypoints:
  kp1: {nl: Een}
  kp2: {nl: Twee}
---

@slide vol layout=bullets keypoints=kp1

@nl
## Veel
- een twee drie vier vijf zes zeven acht negen tien elf twaalf dertien veertien
- b
- c
- d
- e
- f
- g

@script
Intro over de seriele poort.
@step
a
@step
b
@step
c
@step
d
@step
e
@step
f
@step
g
"""


class FakeClaude:
    calls = 0

    def __init__(self, course):
        self.cfg = {"model": "fake", "effort": "low"}
        self.usage = ai.Usage()

    def json(self, system, user, schema, max_tokens=16000):
        FakeClaude.calls += 1
        return {"findings": [
            {"slide_id": "vol", "field": "script", "severity": "warning", "category": "spelling",
             "quote": "seriele poort", "message": "diakriet", "suggestion": "seriële poort"},
            {"slide_id": "", "field": "chapter", "severity": "suggestion", "category": "clarity",
             "quote": "", "message": "algemeen", "suggestion": ""},
        ]}


@pytest.fixture
def course(tmp_path, monkeypatch):
    root = tmp_path / "c"
    (root / "lessen/01").mkdir(parents=True)
    (root / "course.yaml").write_text("title: T\nlangs: [nl, en]\n")
    (root / "lessen/01/01-h.md").write_text(CHAPTER)
    monkeypatch.setattr(ai, "Claude", FakeClaude)
    FakeClaude.calls = 0
    return load_course(root)


def test_fixed_checks(course):
    rep = review.run(course, "nl", Diagnostics(), use_ai=False)
    msgs = [(f.severity, f.category, f.message) for f in rep.findings]
    assert any(c == "density" and "bullets" in m for _, c, m in msgs)
    assert any(c == "density" and "regel van" in m for _, c, m in msgs)
    assert any(s == "warning" and "'kp2' wordt door geen enkele slide" in m for s, _, m in msgs)
    assert any(s == "suggestion" and "'kp1' wordt niet overhoord" in m for s, _, m in msgs)


def test_claude_findings_located_and_cached(course, tmp_path):
    cache = tmp_path / "cache"
    rep = review.run(course, "nl", Diagnostics(), cache_dir=cache)
    spelling = next(f for f in rep.findings if f.category == "spelling")
    assert spelling.line == 21 and spelling.file.endswith("01-h.md")  # the line containing the quote
    assert spelling.suggestion == "seriële poort"
    assert FakeClaude.calls == 1
    rep2 = review.run(course, "nl", Diagnostics(), cache_dir=cache)
    assert FakeClaude.calls == 1 and rep2.cached == 1  # unchanged chapter: from cache
    # sorted: warnings before suggestions
    sev = [f.severity for f in rep.findings]
    assert sev == sorted(sev, key=review.SEVERITIES.index)


def test_markdown_report(course, tmp_path):
    rep = review.run(course, "nl", Diagnostics(), cache_dir=tmp_path / "c2")
    md = rep.as_markdown("T")
    assert md.startswith("# Review: T") and "## warning" in md and "→ seriële poort" in md
