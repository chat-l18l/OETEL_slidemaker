import pytest
from pypdf import PdfReader

from slidesmith.parser import Diagnostics, parse_text
from slidesmith.pdf import build_pdfs, slide_title
from slidesmith.project import load_course

from test_build import make_course


def _chromium_available() -> bool:
    try:
        from slidesmith import browser
        browser.get()
        return True
    except Exception:
        return False


needs_browser = pytest.mark.skipif(not _chromium_available(), reason="geen Chromium (pixi run setup)")


def test_slide_title_fallbacks(tmp_path):
    pf = parse_text("@slide q layout=quote\n@nl\n> Een *mooi* citaat\n@slide x\n@nl\n## Kop\n",
                    tmp_path / "a.md")
    assert slide_title(pf.slides[0], "nl") == "Een mooi citaat"
    assert slide_title(pf.slides[1], "nl") == "Kop"


@needs_browser
def test_pdfs_with_toc_bookmarks_and_contrast_check(tmp_path):
    root = make_course(tmp_path / "cursus")
    chapter = root / "lessen/01-les/01-a.md"
    chapter.write_text(chapter.read_text().replace(
        "## Foto", '## Foto\n<span style="color:#fff">wit op wit</span>\n@reader\nZie [docs](https://example.org/x).'))
    diag = Diagnostics()
    course = load_course(root, diag)
    written = build_pdfs(course, tmp_path / "b", ["nl"], ["slides", "reader"], diag)
    slides, reader = (PdfReader(p) for p in written)

    assert len(slides.pages) == 2 + 3  # title, toc, 3 slides
    assert [o.title for o in slides.outline if not isinstance(o, list)] == ["1. Hoofdstuk A"]

    text = "".join(p.extract_text() for p in reader.pages)
    assert "Inhoud" in text and "Bronnen" in text and "https://example.org/x" in text
    # table of contents got real page numbers in pass 2
    assert "00" not in reader.pages[1].extract_text()

    assert any("weinig contrast" in m and "wit op wit" in m for _, m in diag.warnings)
