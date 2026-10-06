"""The `boxes` diagram DSL: boxes on a grid connected by arrows, rendered to SVG.

    grid 4x4
    box repo "Stap 1 - Repo" at 0,0 step=1
    box idea "Stap 2 - Idee" at 1,0 span=2,1 style=outline
    arrow repo -> idea step=2 label="push"

Coordinates are grid cells (column,row), fractions allowed. Boxes and arrows
with `step=N` appear at reveal step N.
"""

from __future__ import annotations

import html
import re
import shlex
from dataclasses import dataclass

from .model import Loc
from .parser import SourceError

WIDTH = 1760
HEIGHT = 860
FONT_SIZE = 46
MIN_FONT = 22
CHAR_W = 0.5  # average glyph width relative to font size (Questrial)


@dataclass
class Box:
    id: str
    label: str
    col: float
    row: float
    span: tuple[float, float] = (1, 1)
    step: int | None = None
    style: str = "fill"


@dataclass
class Arrow:
    id: str
    src: str
    dst: str
    both: bool = False
    step: int | None = None
    label: str = ""
    style: str = "solid"


@dataclass
class Diagram:
    cols: int = 4
    rows: int = 4
    boxes: dict[str, Box] | None = None
    arrows: list[Arrow] | None = None


def _pair(s: str, loc: Loc) -> tuple[float, float]:
    try:
        a, b = s.split(",")
        return float(a), float(b)
    except ValueError:
        raise SourceError(f"verwacht 'kolom,rij', kreeg {s!r}", loc) from None


def parse(source: str, loc: Loc) -> Diagram:
    d = Diagram(boxes={}, arrows=[])
    for n, line in enumerate(source.splitlines()):
        line_loc = Loc(loc.file, loc.line + 1 + n)
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError as e:
            raise SourceError(f"boxes: {e}", line_loc) from None
        if not tokens:
            continue
        kw = {}
        pos = []
        for t in tokens:
            k, sep, v = t.partition("=")
            if sep and re.fullmatch(r"[a-z]+", k):
                kw[k] = v
            else:
                pos.append(t)
        cmd = pos[0].rstrip(":")
        step = int(kw["step"]) if "step" in kw else None
        if cmd == "grid":
            m = re.fullmatch(r"(\d+)x(\d+)", pos[1] if len(pos) > 1 else "")
            if not m:
                raise SourceError("grid verwacht 'kolommenxrijen', bv. grid 4x4", line_loc)
            d.cols, d.rows = int(m.group(1)), int(m.group(2))
        elif cmd == "box":
            if len(pos) != 5 or pos[3] != "at":
                raise SourceError('verwacht: box <id> "<tekst>" at <kolom>,<rij>', line_loc)
            col, row = _pair(pos[4], line_loc)
            box = Box(id=pos[1], label=pos[2], col=col, row=row, step=step,
                      style=kw.get("style", "fill"))
            if "span" in kw:
                box.span = _pair(kw["span"], line_loc)
            if box.id in d.boxes:
                raise SourceError(f"box '{box.id}' bestaat al", line_loc)
            d.boxes[box.id] = box
        elif cmd == "arrow":
            if len(pos) != 4 or pos[2] not in ("->", "<->"):
                raise SourceError("verwacht: arrow <van> -> <naar>", line_loc)
            for ref in (pos[1], pos[3]):
                if ref not in d.boxes:
                    raise SourceError(f"onbekende box '{ref}' (definieer boxes vóór arrows)", line_loc)
            d.arrows.append(Arrow(
                id=kw.get("id", f"{pos[1]}-{pos[3]}"), src=pos[1], dst=pos[3],
                both=pos[2] == "<->", step=step, label=kw.get("label", ""),
                style=kw.get("style", "solid")))
        else:
            raise SourceError(f"boxes: onbekend commando '{cmd}' (grid, box, arrow)", line_loc)
    return d


@dataclass
class _Placed:
    cx: float
    cy: float
    w: float
    h: float
    fs: float
    lines: list[str]


def _layout(d: Diagram, labels: dict[str, str]) -> dict[str, _Placed]:
    """Box geometry: width follows the text (like hand-made slides), one font size for all."""
    cw, ch = WIDTH / d.cols, HEIGHT / d.rows
    texts = {b.id: labels.get(b.id, b.label).replace("\\n", "\n").split("\n") for b in d.boxes.values()}

    def height(b: Box) -> float:
        return min(b.span[1] * ch * 0.62, 120 * b.span[1])

    def max_w(b: Box) -> float:
        return b.span[0] * cw * 1.2

    fs = FONT_SIZE
    for b in d.boxes.values():
        lines = texts[b.id]
        longest = max(len(x) for x in lines) or 1
        fs = min(fs, height(b) * 0.8 / (len(lines) * 1.15), max_w(b) * 0.88 / (longest * CHAR_W))
    fs = max(MIN_FONT, fs)

    placed = {}
    for b in d.boxes.values():
        lines = texts[b.id]
        longest = max(len(x) for x in lines) or 1
        w = min(max_w(b), max(0.55 * cw * b.span[0], longest * fs * CHAR_W + 1.3 * fs))
        cx = (b.col + b.span[0] / 2) * cw
        cx = min(max(cx, w / 2 + 4), WIDTH - w / 2 - 4)
        cy = (b.row + b.span[1] / 2) * ch
        placed[b.id] = _Placed(cx, cy, w, height(b), fs, lines)
    return placed


def _edge_point(cx, cy, w, h, tx, ty, pad=8.0) -> tuple[float, float]:
    """Point where the ray from the rect centre towards (tx,ty) leaves the rect."""
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    sx = (w / 2 + pad) / abs(dx) if dx else float("inf")
    sy = (h / 2 + pad) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def _frag(step: int | None) -> str:
    return f' class="fragment" data-fragment-index="{step}"' if step else ""


def render(d: Diagram, labels: dict[str, str], uid: str) -> str:
    out = [f'<svg class="boxes" viewBox="0 0 {WIDTH} {HEIGHT}" '
           f'xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">',
           f'<defs><marker id="ah-{uid}" viewBox="0 0 10 10" refX="9" refY="5" '
           f'markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">'
           f'<path d="M0,0 L10,5 L0,10 z" class="bx-head"/></marker></defs>']
    placed = _layout(d, labels)
    for a in d.arrows:
        sp, dp = placed[a.src], placed[a.dst]
        x1, y1 = _edge_point(sp.cx, sp.cy, sp.w, sp.h, dp.cx, dp.cy)
        x2, y2 = _edge_point(dp.cx, dp.cy, dp.w, dp.h, sp.cx, sp.cy)
        dash = ' stroke-dasharray="14 10"' if a.style == "dashed" else ""
        start = f' marker-start="url(#ah-{uid})"' if a.both else ""
        out.append(f'<g{_frag(a.step)}><line class="bx-arrow" x1="{x1:.1f}" y1="{y1:.1f}" '
                   f'x2="{x2:.1f}" y2="{y2:.1f}" marker-end="url(#ah-{uid})"{start}{dash}/>')
        label = labels.get(a.id, a.label)
        if label:
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            out.append(f'<text class="bx-arrow-label" x="{mx:.1f}" y="{my - 14:.1f}" '
                       f'text-anchor="middle">{html.escape(label)}</text>')
        out.append("</g>")
    for b in d.boxes.values():
        p = placed[b.id]
        out.append(f'<g{_frag(b.step)} data-box="{html.escape(b.id)}">'
                   f'<rect class="bx-box bx-{html.escape(b.style)}" x="{p.cx - p.w / 2:.1f}" '
                   f'y="{p.cy - p.h / 2:.1f}" width="{p.w:.1f}" height="{p.h:.1f}"/>')
        y0 = p.cy - (len(p.lines) - 1) * p.fs * 1.15 / 2
        for i, line in enumerate(p.lines):
            out.append(f'<text class="bx-text bx-text-{html.escape(b.style)}" x="{p.cx:.1f}" '
                       f'y="{y0 + i * p.fs * 1.15:.1f}" font-size="{p.fs:.1f}" text-anchor="middle" '
                       f'dominant-baseline="central">{html.escape(line)}</text>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out)


def max_step(d: Diagram) -> int:
    steps = [b.step for b in d.boxes.values() if b.step] + [a.step for a in d.arrows if a.step]
    return max(steps, default=0)
