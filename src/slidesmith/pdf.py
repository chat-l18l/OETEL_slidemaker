"""PDF export: slides PDF (16:9, one slide per page) and reader PDF (A4, slide + reader text).

Both use the print theme. The reader is rendered in two passes: the first pass yields
the page of every chapter/slide (via the PDF's named destinations), the second pass
fills those numbers into the table of contents.
"""

from __future__ import annotations

import datetime
import html
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

from markupsafe import Markup
from pypdf import PdfReader, PdfWriter

from . import browser
from .build import Assets, RenderedSlide, _jinja, _title, copy_static, render_slide
from .mdrender import Ctx, render_plain
from .model import Course, Lesson, Loc, Slide, SOURCE_LANG
from .parser import Diagnostics
from .vcs import version

A4_MARGIN_MM = (18, 18, 22, 18)  # top, right, bottom, left
MM_PX = 96 / 25.4

STRINGS = {
    "nl": {"contents": "Inhoud", "chapter": "Hoofdstuk", "keypoints": "Kernpunten",
           "questions": "Vragen", "answers": "Antwoorden", "sources": "Bronnen",
           "version": "Versie", "generated": "Gegenereerd", "author": "Auteur",
           "language": "Taal", "reader": "Reader", "slides": "Slides", "page": "pagina",
           "open": "open vraag"},
    "en": {"contents": "Contents", "chapter": "Chapter", "keypoints": "Key points",
           "questions": "Questions", "answers": "Answers", "sources": "Sources",
           "version": "Version", "generated": "Generated", "author": "Author",
           "language": "Language", "reader": "Reader", "slides": "Slides", "page": "page",
           "open": "open question"},
}

DEFAULT_OPTS = {"title_page": True, "toc": True, "page_numbers": True, "sources": True, "quiz": True}

_HEADING_RE = re.compile(r"^\s*#{1,3}\s+(.+?)\s*#*\s*$", re.M)
_LINK_RE = re.compile(r'<a href="(https?://[^"]+)"[^>]*>(.*?)</a>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


@dataclass
class PSlide:
    rs: RenderedSlide
    anchor: str
    number: str
    title: str
    reader: Markup | None


@dataclass
class PChapter:
    anchor: str
    number: int
    title: str
    keypoints: list[str]
    slides: list[PSlide] = field(default_factory=list)
    quiz: list[dict] = field(default_factory=list)
    answers: list[str] = field(default_factory=list)


def slide_title(slide: Slide, lang: str) -> str:
    """First heading of the slide; otherwise its first line of text (for a quote, say)."""
    body = slide.block(lang).body
    m = _HEADING_RE.search(body)
    if m:
        return _TAG_RE.sub("", m.group(1)).strip()
    for line in body.splitlines():
        text = re.sub(r"^[>\-*=\s]+|[*_`$]", "", line).strip()
        if text and not text.startswith(("@", "```", "|")):
            return text if len(text) <= 60 else text[:57].rstrip() + "…"
    return slide.id


def _strings(lang: str) -> dict:
    return STRINGS.get(lang, STRINGS["en"])


def collect(course: Course, lesson: Lesson, lang: str, assets: Assets, out: Path,
            diag: Diagnostics) -> tuple[list[PChapter], list[dict]]:
    S = _strings(lang)
    chapters: list[PChapter] = []
    sources: dict[str, str] = {}
    env = {"shared": course.shared}
    for ci, ch in enumerate(lesson.chapters, 1):
        pc = PChapter(anchor=f"ch-{ch.id}", number=ci, title=_title(ch.title, lang),
                      keypoints=[t.get(lang) or t.get(SOURCE_LANG, "") for t in ch.keypoints.values()])
        for si, s in enumerate(ch.slides, 1):
            rs = render_slide(s, lang, course, assets, out / ".cache", Diagnostics(), theme="print")
            b = s.block(lang)
            reader = None
            if b.reader:
                ctx = Ctx(base=(b.loc.file.parent if b.loc else s.loc.file.parent),
                          asset_url=assets.url, uid=f"{s.id}-{lang}-r")
                reader = render_plain(b.reader, ctx, env)
            for url, text in _LINK_RE.findall(str(reader or "") + str(rs.body)):
                sources.setdefault(url, html.unescape(_TAG_RE.sub("", text)).strip() or url)
            pc.slides.append(PSlide(rs=rs, anchor=f"p-{ch.id}-{s.id}", number=f"{ci}.{si}",
                                    title=slide_title(s, lang), reader=Markup(reader) if reader else None))
        for q in ch.quizzes:
            for question in q.questions:
                t = question.langs.get(lang) or question.langs.get(SOURCE_LANG)
                if t is None:
                    continue
                pc.quiz.append({"text": t.text, "options": [{"text": o.text} for o in t.options]})
                correct = [o.text for o in t.options if o.correct]
                pc.answers.append(", ".join(correct) if correct else f"({S['open']})")
        chapters.append(pc)
    return chapters, [{"url": u, "title": t} for u, t in sources.items()]


def _page(pages: dict[str, int] | None, anchor: str) -> str:
    # pass 1 uses a same-width placeholder so the layout does not shift in pass 2
    return str(pages[anchor]) if pages and anchor in pages else "00"


def _toc(chapters: list[PChapter], pages: dict[str, int] | None, slides_pdf: bool) -> list[dict]:
    toc = []
    for ch in chapters:
        first = ch.slides[0].anchor if ch.slides else ch.anchor
        toc.append({"anchor": first if slides_pdf else ch.anchor, "level": 1,
                    "number": str(ch.number), "title": ch.title,
                    "page": "" if slides_pdf else _page(pages, ch.anchor)})
        for s in ch.slides:
            toc.append({"anchor": s.anchor, "level": 2, "number": s.number, "title": s.title,
                        "page": "" if slides_pdf else _page(pages, s.anchor)})
    return toc


def _render_pdf(html_path: Path, pdf_kwargs: dict, diag: Diagnostics, check: bool) -> bytes:
    page = browser.get().new_page()
    try:
        page.goto(html_path.as_uri())
        page.wait_for_function("window.__ready === true", timeout=60_000)
        if check:
            for w in page.evaluate("window.__warnings"):
                diag.warn(Loc(html_path, 1), w)
        return page.pdf(print_background=True, **pdf_kwargs)
    finally:
        page.close()


def _named_pages(data: bytes) -> dict[str, int]:
    r = PdfReader(io.BytesIO(data))
    return {name.lstrip("/"): r.get_destination_page_number(d) + 1
            for name, d in r.named_destinations.items()}


def _footer(text: str, S: dict) -> str:
    style = "font-family:Questrial,sans-serif;font-size:7.5pt;color:#777;width:100%;padding:0 18mm;display:flex;justify-content:space-between"
    return (f'<div style="{style}"><span>{html.escape(text)}</span>'
            f'<span>{S["page"]} <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


def build_lesson_pdfs(course: Course, lesson: Lesson, lang: str, out: Path, assets: Assets,
                      kinds: list[str], diag: Diagnostics) -> list[Path]:
    S = _strings(lang)
    opts = {**DEFAULT_OPTS, **(course.config.get("pdf") or {})}
    chapters, sources = collect(course, lesson, lang, assets, out, diag)
    ver = version(course.root)
    base = {
        "lang": lang, "S": S, "static": "../static", "accent": course.config["accent"],
        "course_title": _title(course.title, lang), "lesson_title": _title(lesson.title, lang),
        "author": course.config.get("author", ""), "version": str(ver),
        "today": datetime.date.today().isoformat(), "opts": opts,
        "logo_position": course.config["logo_position"], "chapters": chapters,
    }
    tmpl = _jinja().get_template("print.html.j2")
    work = out / "print"
    work.mkdir(parents=True, exist_ok=True)
    target_dir = out / "pdf" / lang
    target_dir.mkdir(parents=True, exist_ok=True)
    written = []
    stem = f"{lesson.id}-{lang}"

    if "slides" in kinds:
        doc = tmpl.render(**base, mode="slides", doc_title=f"{base['lesson_title']} — {S['slides']}",
                          scale=1, page_size="1920px 1080px", page_margin="0", toc_per_page=28,
                          toc=_toc(chapters, None, slides_pdf=True))
        p = work / f"{stem}-slides.html"
        p.write_text(doc, encoding="utf-8")
        data = _render_pdf(p, {"width": "1920px", "height": "1080px",
                               "margin": {"top": "0", "right": "0", "bottom": "0", "left": "0"}},
                           diag, check=True)
        target = target_dir / f"{lesson.id}-slides.pdf"
        _finish(data, None, target, base, S["slides"], chapters, slides_pdf=True)
        written.append(target)

    if "reader" in kinds:
        t, r, b, l = A4_MARGIN_MM
        content_w = (210 - l - r) * MM_PX
        common = dict(**base, mode="reader", doc_title=f"{base['lesson_title']} — {S['reader']}",
                      scale=round(content_w / 1920, 5), page_size="A4",
                      page_margin=f"{t}mm {r}mm {b}mm {l}mm", answers=[
                          {"number": c.number, "title": c.title, "items": c.answers}
                          for c in chapters if c.answers],
                      sources=sources)
        pdf_kwargs = {"format": "A4", "display_header_footer": opts["page_numbers"],
                      "header_template": "<span></span>",
                      "footer_template": _footer(f"{base['course_title']} · {base['lesson_title']}", S),
                      "margin": {"top": f"{t}mm", "right": f"{r}mm", "bottom": f"{b}mm", "left": f"{l}mm"}}
        p = work / f"{stem}-reader.html"
        # pass 1: find pages
        p.write_text(tmpl.render(**common, toc=_toc(chapters, None, slides_pdf=False)), encoding="utf-8")
        pages = _named_pages(_render_pdf(p, pdf_kwargs, diag, check=False))
        # pass 2: final, with page numbers in the table of contents
        p.write_text(tmpl.render(**common, toc=_toc(chapters, pages, slides_pdf=False)), encoding="utf-8")
        body = _render_pdf(p, pdf_kwargs, diag, check=True)
        title = None
        if opts["title_page"]:
            tp = work / f"{stem}-title.html"
            tp.write_text(tmpl.render(**{**common, "mode": "title"}, toc=[]), encoding="utf-8")
            title = _render_pdf(tp, {"format": "A4", "margin": pdf_kwargs["margin"]}, diag, check=False)
        target = target_dir / f"{lesson.id}-reader.pdf"
        _finish(body, title, target, base, S["reader"], chapters, slides_pdf=False)
        written.append(target)
    return written


def _finish(body: bytes, title: bytes | None, target: Path, base: dict, kind: str,
            chapters: list[PChapter], slides_pdf: bool) -> None:
    """Merge title page + body, add bookmarks and metadata."""
    writer = PdfWriter()
    offset = 0
    if title:
        writer.append(PdfReader(io.BytesIO(title)))
        offset = len(writer.pages)
    body_reader = PdfReader(io.BytesIO(body))
    writer.append(body_reader)
    pages = {name.lstrip("/"): body_reader.get_destination_page_number(d)
             for name, d in body_reader.named_destinations.items()}
    for ch in chapters:
        key = ch.slides[0].anchor if slides_pdf and ch.slides else ch.anchor
        if key not in pages:
            continue
        parent = writer.add_outline_item(f"{ch.number}. {ch.title}", pages[key] + offset)
        for s in ch.slides:
            if s.anchor in pages:
                writer.add_outline_item(f"{s.number} {s.title}", pages[s.anchor] + offset, parent=parent)
    writer.add_metadata({
        "/Title": f"{base['lesson_title']} — {kind}",
        "/Subject": base["course_title"],
        "/Author": base["author"] or "",
        "/Keywords": base["version"],
    })
    writer.page_mode = "/UseOutlines"
    with open(target, "wb") as f:
        writer.write(f)


def build_pdfs(course: Course, out: Path, langs: list[str], kinds: list[str],
               diag: Diagnostics) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    copy_static(out)
    assets = Assets(out, diag)
    written = []
    for lang in langs:
        for lesson in course.lessons:
            written += build_lesson_pdfs(course, lesson, lang, out, assets, kinds, diag)
    return written
