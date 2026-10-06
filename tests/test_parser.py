from pathlib import Path

import pytest

from slidesmith.parser import Diagnostics, SourceError, parse_text, src_hash

P = Path("/tmp/x/h01.md")


def parse(text: str):
    diag = Diagnostics()
    return parse_text(text, P, Path("/tmp/x/shared"), diag), diag


def test_slide_with_languages_script_steps_reader_notes():
    pf, diag = parse("""---
id: h01
---

@slide a layout=bullets keypoints=k1

@nl
## Titel
- een
- twee

@script
Intro.
@step
Eerste.
@step
Tweede.

@reader
Uitleg.

@notes
Notitie.

@en src=abc
## Title
""")
    (s,) = pf.slides
    assert s.id == "a" and s.layout == "bullets" and s.keypoints == ["k1"]
    nl = s.langs["nl"]
    assert nl.body == "## Titel\n- een\n- twee"
    assert nl.script == ["Intro.", "Eerste.", "Tweede."]
    assert nl.reader == "Uitleg."
    assert nl.notes == "Notitie."
    assert s.langs["en"].src == "abc"
    assert not diag.warnings


def test_directives_inside_code_fence_are_content():
    pf, _ = parse("""@slide c layout=code
@nl
```python
@slide not-a-slide
```
""")
    (s,) = pf.slides
    assert "@slide not-a-slide" in s.langs["nl"].body


def test_unknown_directive_is_an_error_with_location():
    with pytest.raises(SourceError) as e:
        parse("@slide a\n@nl\n@foo bar\n")
    assert e.value.loc.line == 3


def test_double_at_escapes_literal_at():
    pf, _ = parse("@slide a\n@nl\n@@home is een gebruikersnaam\n")
    assert pf.slides[0].langs["nl"].body == "@home is een gebruikersnaam"


def test_unknown_layout():
    with pytest.raises(SourceError, match="onbekende layout"):
        parse("@slide a layout=nope\n")


def test_visuals_must_precede_language_blocks():
    with pytest.raises(SourceError, match="vóór de taalblokken"):
        parse("@slide a\n@nl\n@image foo.png\n")


def test_callouts_parse_percentages_and_labels():
    pf, _ = parse("""@slide b layout=callouts
@image board.png
@callout circle at 10%,20% r=5% label="Poort" label.en="Port" step=1
@callout arrow from 1%,2% to 3%,4% label=X
@nl
## Bord
""")
    s = pf.slides[0]
    c1, c2 = s.callouts
    assert (c1.kind, c1.at, c1.r, c1.step) == ("circle", (10.0, 20.0), 5.0, 1)
    assert c1.label == {"nl": "Poort", "en": "Port"}
    assert c2.to == (3.0, 4.0) and c2.step is None


def test_hash_changes_with_nl_and_visuals_but_not_en():
    base = "@slide a layout=diagram\n@diagram boxes\nbox x \"A\" at 0,0\n@nl\n## T\n@en src=1\n## T\n"
    h = src_hash(parse(base)[0].slides[0])
    assert h == src_hash(parse(base.replace("## T\n@en src=1\n## T", "## T\n@en src=1\n## Other"))[0].slides[0])
    assert h != src_hash(parse(base.replace("@nl\n## T", "@nl\n## U"))[0].slides[0])
    assert h != src_hash(parse(base.replace('"A"', '"B"'))[0].slides[0])


def test_step_outside_script_is_error():
    with pytest.raises(SourceError, match="@step"):
        parse("@slide a\n@nl\ntekst\n@step\n")


def test_quiz():
    pf, _ = parse("""@quiz q1
@question mc keypoint=k
@nl Welke?
- [ ] a
- [x] b
@en src=ff Which?
- [x] B
""")
    (q,) = pf.quizzes[0].questions
    assert q.kind == "mc" and q.keypoint == "k"
    assert q.langs["nl"].text == "Welke?"
    assert [o.correct for o in q.langs["nl"].options] == [False, True]
    assert q.langs["en"].src == "ff"
