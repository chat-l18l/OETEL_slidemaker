"""Callouts (circles, arrows, boxes with labels) drawn over an image as SVG."""

from __future__ import annotations

import html
import re
from pathlib import Path

from PIL import Image

from .model import Callout


def image_size(path: Path) -> tuple[int, int]:
    if path.suffix.lower() == ".svg":
        head = path.read_text(encoding="utf-8", errors="replace")[:4000]
        m = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head)
        if m:
            return int(float(m.group(1))), int(float(m.group(2)))
        w = re.search(r'width="([\d.]+)', head)
        h = re.search(r'height="([\d.]+)', head)
        if w and h:
            return int(float(w.group(1))), int(float(h.group(1)))
        return 1600, 900
    with Image.open(path) as im:
        return im.size


def _frag(step: int | None) -> str:
    return f' class="fragment" data-fragment-index="{step}"' if step else ""


def _label(x: float, y: float, text: str, fs: float, anchor: str) -> str:
    if not text:
        return ""
    w = len(text) * fs * 0.56 + fs * 0.9
    h = fs * 1.5
    rx = {"start": x, "end": x - w, "middle": x - w / 2}[anchor]
    tx = {"start": x + fs * 0.45, "end": x - fs * 0.45, "middle": x}[anchor]
    return (f'<rect class="co-label-bg" x="{rx:.1f}" y="{y - h / 2:.1f}" width="{w:.1f}" '
            f'height="{h:.1f}" rx="{fs * 0.25:.1f}"/>'
            f'<text class="co-label" x="{tx:.1f}" y="{y:.1f}" font-size="{fs:.1f}" '
            f'text-anchor="{anchor}" dominant-baseline="central">{html.escape(text)}</text>')


def render(img_url: str, size: tuple[int, int], callouts: list[Callout], lang: str,
           labels: dict[str, str], uid: str) -> str:
    W, H = size
    sw = max(W, H) * 0.005
    fs = W * 0.026
    parts = [f'<div class="callout-stage" style="aspect-ratio:{W}/{H}">',
             f'<img src="{html.escape(img_url)}" alt="">',
             f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">',
             f'<defs><marker id="coh-{uid}" viewBox="0 0 10 10" refX="8" refY="5" '
             f'markerWidth="5" markerHeight="5" orient="auto"><path d="M0,0 L10,5 L0,10 z" '
             f'class="co-head"/></marker></defs>']
    for c in callouts:
        text = labels.get(c.id) or c.label.get(lang) or c.label.get("nl", "")
        x, y = c.at[0] / 100 * W, c.at[1] / 100 * H
        parts.append(f'<g{_frag(c.step)}>')
        if c.kind == "circle":
            r = c.r / 100 * W
            parts.append(f'<circle class="co-shape" cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                         f'stroke-width="{sw:.1f}"/>')
            right = c.at[0] < 70
            lx = x + r + fs * 0.6 if right else x - r - fs * 0.6
            parts.append(_label(lx, y, text, fs, "start" if right else "end"))
        elif c.kind == "box":
            w, h = c.size[0] / 100 * W, c.size[1] / 100 * H
            parts.append(f'<rect class="co-shape" x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                         f'height="{h:.1f}" stroke-width="{sw:.1f}"/>')
            parts.append(_label(x, y - fs * 1.1, text, fs, "start"))
        else:
            x2, y2 = c.to[0] / 100 * W, c.to[1] / 100 * H
            parts.append(f'<line class="co-shape" x1="{x:.1f}" y1="{y:.1f}" x2="{x2:.1f}" '
                         f'y2="{y2:.1f}" stroke-width="{sw:.1f}" marker-end="url(#coh-{uid})"/>')
            anchor = "end" if x2 > x else "start"
            parts.append(_label(x, y, text, fs, anchor))
        parts.append("</g>")
    parts.append("</svg></div>")
    return "".join(parts)


def max_step(callouts: list[Callout]) -> int:
    return max((c.step or 0 for c in callouts), default=0)
