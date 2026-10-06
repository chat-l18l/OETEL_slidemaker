"""Build HTML presentations (reveal.js) from a course."""

from __future__ import annotations

import hashlib
import html
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from . import boxes, callouts, diagrams
from .mdrender import Ctx, pygments_css, render_body, render_plain
from .model import Course, Lesson, Loc, Slide, SOURCE_LANG
from .parser import Diagnostics, SourceError
from .timing import step_durations

PKG = Path(__file__).parent
STATIC = PKG / "static"
AUTO_STEP_LAYOUTS = {"bullets"}


class Assets:
    """Copies referenced files into build/media under a content-hashed name."""

    def __init__(self, out: Path, diag: Diagnostics):
        self.dir = out / "media"
        self.diag = diag
        self.loc: Loc | None = None
        self._done: dict[Path, str] = {}

    def url(self, path: Path) -> str:
        path = path.resolve()
        if path in self._done:
            return self._done[path]
        if not path.exists():
            self.diag.warn(self.loc, f"bestand niet gevonden: {path}")
            return ""
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:10]
        name = f"{path.stem}-{digest}{path.suffix.lower()}"
        self.dir.mkdir(parents=True, exist_ok=True)
        target = self.dir / name
        if not target.exists():
            shutil.copy2(path, target)
        self._done[path] = f"../media/{name}"
        return self._done[path]


@dataclass
class RenderedSlide:
    id: str
    anchor: str
    layout: str
    classes: list[str]
    body: Markup
    visual: Markup | None
    notes: Markup | None
    logo: str | None
    steps: int
    durations: list[float] = field(default_factory=list)


def _notes_html(slide: Slide, lang: str, ctx: Ctx, env: dict) -> str:
    b = slide.block(lang)
    parts = []
    if b.script and any(b.script):
        segs = []
        for i, seg in enumerate(b.script):
            if seg:
                segs.append(f'<p><b class="step-mark">[{i}]</b> {html.escape(seg)}</p>')
        parts.append('<div class="script">' + "".join(segs) + "</div>")
    if b.notes:
        parts.append('<div class="presenter-notes">' + render_plain(b.notes, ctx, env) + "</div>")
    return "\n".join(parts)


def render_slide(slide: Slide, lang: str, course: Course, assets: Assets, cache: Path,
                 diag: Diagnostics, theme: str = "dark") -> RenderedSlide:
    b = slide.block(lang)
    assets.loc = slide.loc
    base = (b.loc.file.parent if b.loc else slide.loc.file.parent)
    steps_opt = slide.options.get("steps", "auto" if slide.layout in AUTO_STEP_LAYOUTS else "none")
    ctx = Ctx(base=base, asset_url=assets.url, uid=f"{slide.id}-{lang}",
              auto_steps=steps_opt == "auto")
    env = {"shared": course.shared}
    nl_labels = slide.langs[SOURCE_LANG].labels if SOURCE_LANG in slide.langs else {}
    labels = {**nl_labels, **b.labels}

    body = render_body(b.body, ctx, env) if b.body.strip() else ""
    visual = None
    max_visual = 0
    if slide.diagram:
        d = slide.diagram
        if d.kind == "boxes":
            parsed = boxes.parse(d.source, d.loc)
            visual = boxes.render(parsed, labels, ctx.uid)
            max_visual = boxes.max_step(parsed)
        else:
            visual = diagrams.render_external(d, cache / "diagrams", theme)
    if slide.image:
        url = assets.url(slide.image.path)
        if slide.callouts and slide.image.path.exists():
            size = callouts.image_size(slide.image.path)
            visual = callouts.render(url, size, slide.callouts, lang, labels, ctx.uid)
            max_visual = callouts.max_step(slide.callouts)
        else:
            visual = f'<img class="main-image" src="{html.escape(url)}" alt="">'
    elif slide.callouts:
        raise SourceError("@callout vereist een @image op dezelfde slide", slide.loc)

    steps = max(ctx.step, max_visual)
    if b.script and len(b.script) - 1 != steps:
        diag.warn(b.loc, f"slide '{slide.id}' ({lang}): script heeft {len(b.script) - 1} @step-"
                         f"fragmenten, de slide heeft {steps} onthulstappen")

    classes = []
    if pos := slide.options.get("title"):
        classes.append(f"title-{pos}")
    if extra := slide.options.get("class"):
        classes.extend(extra.split(","))
    logo = None
    if course.config.get("logo") and slide.options.get("logo", "on") != "off":
        logo = assets.url(course.root / course.config["logo"])

    wpm = course.config["wpm"].get(lang, 140)
    return RenderedSlide(
        id=slide.id,
        anchor=f"s-{slide.id}",
        layout=slide.layout,
        classes=classes,
        body=Markup(body),
        visual=Markup(visual) if visual else None,
        notes=Markup(_notes_html(slide, lang, ctx, env)) or None,
        logo=logo,
        steps=steps,
        durations=step_durations(b.script, steps, wpm),
    )


def _jinja() -> Environment:
    return Environment(loader=FileSystemLoader(PKG / "templates"),
                       autoescape=select_autoescape(["html", "j2"]))


def _title(d: dict[str, str], lang: str) -> str:
    return d.get(lang) or d.get(SOURCE_LANG) or next(iter(d.values()), "")


def build_lesson(course: Course, lesson: Lesson, lang: str, out: Path, assets: Assets,
                 diag: Diagnostics, live: bool = False) -> Path:
    rendered: list[RenderedSlide] = []
    timeline_slides = []
    chapters = []
    t = 0.0
    for ci, ch in enumerate(lesson.chapters):
        ch_start = t
        for s in ch.slides:
            r = render_slide(s, lang, course, assets, out / ".cache", diag)
            rendered.append(r)
            timeline_slides.append({"id": s.id, "chapter": ci, "start": round(t, 2),
                                    "steps": [round(x, 2) for x in r.durations]})
            t += sum(r.durations)
        chapters.append({"title": _title(ch.title, lang), "start": round(ch_start, 2),
                         "dur": round(t - ch_start, 2)})
    deck = {
        "lang": lang,
        "lesson": lesson.id,
        "total": round(t, 2),
        "chapters": chapters,
        "slides": timeline_slides,
        "live": live,
    }
    page = _jinja().get_template("deck.html.j2").render(
        lang=lang,
        title=f"{_title(lesson.title, lang)} — {_title(course.title, lang)}",
        static="../static",
        accent=course.config["accent"],
        slides=rendered,
        logo_position=course.config["logo_position"],
        timebar=course.config["timebar"],
        deck_json=Markup(json.dumps(deck, ensure_ascii=False).replace("</", "<\\/")),
    )
    target = out / lang / f"{lesson.id}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target


def build_index(course: Course, lang: str, out: Path) -> Path:
    page = _jinja().get_template("index.html.j2").render(
        lang=lang,
        title=_title(course.title, lang),
        static="../static",
        accent=course.config["accent"],
        langs=course.langs,
        lessons=[{
            "href": f"{lesson.id}.html",
            "title": _title(lesson.title, lang),
            "chapters": [_title(ch.title, lang) for ch in lesson.chapters],
        } for lesson in course.lessons],
    )
    target = out / lang / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(page, encoding="utf-8")
    return target


def copy_static(out: Path) -> None:
    dst = out / "static"
    shutil.copytree(STATIC, dst, dirs_exist_ok=True)
    (dst / "pygments.css").write_text(pygments_css(), encoding="utf-8")


def build(course: Course, out: Path, langs: list[str], diag: Diagnostics,
          live: bool = False) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    copy_static(out)
    assets = Assets(out, diag)
    written = []
    for lang in langs:
        for lesson in course.lessons:
            written.append(build_lesson(course, lesson, lang, out, assets, diag, live))
        written.append(build_index(course, lang, out))
    (out / "index.html").write_text(
        f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0; url={langs[0]}/index.html">',
        encoding="utf-8")
    return written
