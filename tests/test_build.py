from pathlib import Path

from PIL import Image

from slidesmith.build import build
from slidesmith.parser import Diagnostics
from slidesmith.project import check_translations, load_course
from slidesmith.translations import stamp


def make_course(root: Path) -> Path:
    (root / "lessen/01-les").mkdir(parents=True)
    (root / "shared/slides").mkdir(parents=True)
    (root / "course.yaml").write_text("title: Test\nlangs: [nl, en]\n")
    Image.new("RGB", (200, 100)).save(root / "lessen/01-les/foto.png")
    (root / "shared/slides/outro.md").write_text("@slide outro layout=title\n@nl\n# Einde\n")
    (root / "lessen/01-les/01-a.md").write_text("""---
title: {nl: Hoofdstuk A, en: Chapter A}
---
@slide lijst layout=bullets
@nl
## Lijst
- een
- twee
=> conclusie
@script
Intro.
@step
Een.
@step
Twee.
@step
Dus.
@en src=old
## List
- one
- two
=> conclusion

@slide foto layout=callouts
@image foto.png
@callout circle at 50%,50% label=Hier label.en=Here step=1
@nl
## Foto

@include @shared/slides/outro.md
""")
    return root


def test_build_and_translations(tmp_path):
    root = make_course(tmp_path / "cursus")
    diag = Diagnostics()
    course = load_course(root, diag)
    out = tmp_path / "build"
    written = build(course, out, ["nl", "en"], diag)
    assert out / "nl" / "01-les.html" in written
    nl = (out / "nl" / "01-les.html").read_text()
    en = (out / "en" / "01-les.html").read_text()
    # list items + takeaway are steps 1..3
    assert nl.count('class="fragment"') >= 2 and 'takeaway fragment" data-fragment-index="3"' in nl
    assert ">Hier<" in nl and ">Here<" in en
    assert 'id="s-outro"' in nl
    assert list((out / "media").glob("foto-*.png"))
    assert not diag.warnings  # script segments match steps

    check_translations(course, diag)
    msgs = [m for _, m in diag.warnings]
    assert any("'lijst'" in m and "verouderd" in m for m in msgs)
    assert any("'foto'" in m and "ontbreekt" in m for m in msgs)

    stamp(course, "en")
    diag2 = Diagnostics()
    check_translations(load_course(root, diag2), diag2)
    assert not any("'lijst'" in m for _, m in diag2.warnings)


def test_timeline_in_page(tmp_path):
    root = make_course(tmp_path / "cursus")
    diag = Diagnostics()
    build(load_course(root, diag), tmp_path / "b", ["nl"], diag)
    page = (tmp_path / "b/nl/01-les.html").read_text()
    assert '"chapters": [{"title": "Hoofdstuk A"' in page
