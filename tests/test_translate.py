import json

import pytest

from slidesmith import ai, translate
from slidesmith.parser import Diagnostics, src_hash
from slidesmith.project import check_translations, load_course

CHAPTER = """---
title:
  nl: Hoofdstuk
keypoints:
  kp:
    nl: Een kernpunt.
---

@slide lijst layout=bullets keypoints=kp

@nl
## Lijst
- een
- twee
=> dus

@script
Intro.
@step
Een.
@step
Twee.
@step
Dus.

@reader
Zie [docs](https://example.org).


@slide diag layout=diagram

@diagram boxes
box a "Stap A" at 0,0 step=1

@nl
## Diagram
@script
Kijk.
@step
Stap A.

@en src=oud
## Diagram
@labels a="Step A"
@script
Look.
@step
Step A.


@quiz q
@question mc keypoint=kp
@nl Wat?
- [ ] dit
- [x] dat
"""


class FakeClaude:
    """Translates by prefixing 'EN ' and keeps the structure; can break it once on purpose."""

    calls: list = []
    break_first = False

    def __init__(self, course):
        self.cfg = {"model": "fake", "effort": "low"}
        self.usage = ai.Usage()

    def json(self, system, user, schema, max_tokens=16000):
        req = json.loads(user.split("\n\nYour previous answer")[0])
        FakeClaude.calls.append(req)
        if req["unit"] == "slide":
            nl = req["nl"]
            body = "\n".join(("- EN " + line[2:]) if line.startswith("- ") else
                             ("=> EN " + line[3:]) if line.startswith("=> ") else line
                             for line in nl["body"].splitlines())
            out = {"body": body, "script": ["EN " + s for s in nl["script"]],
                   "reader": "EN " + nl["reader"] if nl["reader"] else "", "notes": "",
                   "labels": [{"id": x["id"], "text": "EN " + x["text"]} for x in req["labels_nl"]]}
            if FakeClaude.break_first and len(FakeClaude.calls) == 1:
                out["script"] = out["script"][:1]
            return out
        if req["unit"] == "chapter_header":
            return {"title": "EN " + req["title_nl"],
                    "keypoints": [{"id": k["id"], "text": "EN " + k["text"]} for k in req["keypoints_nl"]]}
        return {"questions": [{"id": q["id"], "text": "EN " + q["text"],
                               "options": ["EN " + o for o in q["options"]]} for q in req["questions"]]}


@pytest.fixture
def course(tmp_path, monkeypatch):
    root = tmp_path / "c"
    (root / "lessen/01").mkdir(parents=True)
    (root / "course.yaml").write_text("title: T\nlangs: [nl, en]\n")
    (root / "glossary.yaml").write_text("keep: [firmware]\nterms: {werkbank: workbench}\n")
    (root / "lessen/01/01-h.md").write_text(CHAPTER)
    monkeypatch.setattr(ai, "Claude", FakeClaude)
    FakeClaude.calls = []
    FakeClaude.break_first = False
    return root


def test_signature_and_check():
    nl = {"body": "## T\n- a\n- b\n=> c\n```py\nx\ny\n```", "script": ["", "a", "b", "c"]}
    good = {"body": "## T\n- A\n- B\n=> C\n```py\nX\nY\n```", "script": ["", "A", "B", "C"], "labels": []}
    assert translate.check_slide(nl, good, set()) == []
    bad = {**good, "body": "## T\n- A\n=> C\n```py\nX\n```"}
    errors = translate.check_slide(nl, bad, set())
    assert any("lijstitems" in e for e in errors) and any("codeblokken" in e for e in errors)


def test_glossary_text(course):
    c = load_course(course)
    text = translate.glossary_text(translate.load_glossary(c))
    assert "werkbank → workbench" in text and "firmware" in text


def test_translate_everything(course):
    diag = Diagnostics()
    c = load_course(course, diag)
    done, usage, model = translate.run(c, "en", diag)
    assert set(done) >= {"slide lijst", "slide diag", "hoofdstukkop 01-h", "quizvraag 01-h#1"}
    text = (course / "lessen/01/01-h.md").read_text()
    # new EN block inserted after the NL block, with a fresh hash and structure intact
    assert "- EN een" in text and "=> EN dus" in text and "@step\nEN Twee." in text
    assert "EN Zie [docs](https://example.org)." in text
    # outdated block replaced, label from the boxes diagram translated
    assert "@en src=oud" not in text and '@labels a="EN Stap A"' in text and "Look." not in text
    # quiz with correct flags kept, front matter extended
    assert "- [x] EN dat" in text and '  en: "EN Hoofdstuk"' in text and '    en: "EN Een kernpunt."' in text

    diag2 = Diagnostics()
    c2 = load_course(course, diag2)
    check_translations(c2, diag2)
    assert diag2.warnings == []
    ch = c2.lessons[0].chapters[0]
    assert all(s.langs["en"].src == src_hash(s) for s in ch.slides)
    # nothing left to do
    assert translate.run(c2, "en", Diagnostics())[0] == []


def test_retry_after_broken_structure(course):
    FakeClaude.break_first = True
    diag = Diagnostics()
    done, _, _ = translate.run(load_course(course, diag), "en", diag, ids={"lijst"})
    assert done == ["slide lijst"]
    slide_calls = [c for c in FakeClaude.calls if c["unit"] == "slide"]
    assert len(slide_calls) == 2  # first answer rejected, second accepted


def test_previous_translation_is_sent_for_outdated(course):
    translate.run(load_course(course), "en", Diagnostics(), ids={"diag"})
    (req,) = [c for c in FakeClaude.calls if c["unit"] == "slide"]
    assert req["previous_en"]["script"] == ["Look.", "Step A."]
