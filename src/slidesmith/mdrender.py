"""Markdown → HTML for slide bodies, reader text and notes."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import TextLexer, get_lexer_by_name
from pygments.util import ClassNotFound

_TAKEAWAY_RE = re.compile(r"^=>\s+(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
# drawn instead of the "→" glyph, which is missing from most slide fonts
ARROW_SVG = ('<svg class="arrow" viewBox="0 0 40 24" aria-hidden="true"><path d="M2 12 H34 M24 3 L36 12 L24 21" '
             'fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round"/></svg>')


@dataclass
class Ctx:
    """Per-slide rendering context."""

    base: Path  # directory relative paths are resolved against
    asset_url: Callable[[Path], str]
    uid: str
    auto_steps: bool = False
    step: int = 0  # last assigned step

    def next_step(self) -> int:
        self.step += 1
        return self.step


def _math_inline(self, tokens, idx, options, env):
    return f'<span class="math">\\({html.escape(tokens[idx].content)}\\)</span>'


def _math_block(self, tokens, idx, options, env):
    return f'<div class="math">\\[{html.escape(tokens[idx].content)}\\]</div>\n'


def _parse_info(info: str) -> tuple[str, dict[str, str]]:
    parts = info.split()
    lang = parts[0] if parts else ""
    opts = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
    return lang, opts


def _line_groups(spec: str) -> list[list[int]]:
    groups = []
    for grp in spec.split("|"):
        lines: list[int] = []
        for part in grp.split(","):
            a, _, b = part.partition("-")
            if a.strip().isdigit():
                lines.extend(range(int(a), int(b or a) + 1))
        groups.append(lines)
    return groups


def render_code(code: str, info: str, ctx: Ctx | None) -> str:
    lang, opts = _parse_info(info)
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    prefix = f"{ctx.uid}-c{ctx.step}" if ctx else "c"
    fmt = HtmlFormatter(cssclass="code", linespans=prefix, wrapcode=True)
    out = highlight(code, lexer, fmt)
    if ctx and "steps" in opts:
        frags = "".join(
            f'<span class="fragment code-step" data-fragment-index="{ctx.next_step()}" '
            f'data-lines="{",".join(map(str, g))}"></span>'
            for g in _line_groups(opts["steps"])
        )
        out = f'<div class="code-wrap" data-prefix="{prefix}">{out}{frags}</div>'
    return out


def make_md(ctx: Ctx | None) -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "typographer": True}).enable(["table", "strikethrough"])
    md.use(dollarmath_plugin, double_inline=True)
    md.add_render_rule("math_inline", _math_inline)
    md.add_render_rule("math_inline_double", _math_block)
    md.add_render_rule("math_block", _math_block)
    md.add_render_rule("math_block_label", _math_block)

    def fence(self, tokens, idx, options, env):
        t = tokens[idx]
        return render_code(t.content, t.info, ctx)

    md.add_render_rule("fence", fence)

    if ctx is not None:
        default_image = md.renderer.rules.get("image")

        def image(self, tokens, idx, options, env):
            t = tokens[idx]
            src = t.attrGet("src") or ""
            if src and not re.match(r"^[a-z]+:", src):
                if src.startswith("@shared/"):
                    path = env["shared"] / src[len("@shared/"):]
                else:
                    path = ctx.base / src
                t.attrSet("src", ctx.asset_url(path))
            return default_image(tokens, idx, options, env)

        md.add_render_rule("image", image)
    return md


def _assign_list_steps(tokens, ctx: Ctx) -> None:
    depth = 0
    for t in tokens:
        if t.type in ("bullet_list_open", "ordered_list_open"):
            depth += 1
        elif t.type in ("bullet_list_close", "ordered_list_close"):
            depth -= 1
        elif t.type == "list_item_open" and depth == 1:
            t.attrJoin("class", "fragment")
            t.attrSet("data-fragment-index", str(ctx.next_step()))


def render_markdown(text: str, ctx: Ctx, env: dict, steps: bool) -> str:
    md = make_md(ctx)
    tokens = md.parse(text, env)
    if steps:
        _assign_list_steps(tokens, ctx)
    return md.renderer.render(tokens, md.options, env)


def _segments(text: str) -> list[tuple[str, str]]:
    """Split into ('md', text) and ('takeaway', text) segments, respecting code fences."""
    segs: list[tuple[str, str]] = []
    buf: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _TAKEAWAY_RE.match(line)
        if m:
            if buf:
                segs.append(("md", "\n".join(buf)))
                buf = []
            segs.append(("takeaway", m.group(1)))
        else:
            buf.append(line)
    if buf:
        segs.append(("md", "\n".join(buf)))
    return segs


def render_body(text: str, ctx: Ctx, env: dict) -> str:
    """Render a slide body; handles `@col` columns and `=>` takeaway lines."""
    columns = re.split(r"(?m)^@col\s*$", text)
    rendered = []
    for col in columns:
        parts = []
        for kind, seg in _segments(col):
            if kind == "md":
                parts.append(render_markdown(seg, ctx, env, ctx.auto_steps))
            else:
                inline = make_md(ctx).renderInline(seg, env)
                frag = (f' class="takeaway fragment" data-fragment-index="{ctx.next_step()}"'
                        if ctx.auto_steps else ' class="takeaway"')
                parts.append(f'<p{frag}>{ARROW_SVG} {inline}</p>')
        rendered.append("\n".join(parts))
    if len(rendered) == 1:
        return rendered[0]
    return '<div class="columns">' + "".join(f'<div class="col">{c}</div>' for c in rendered) + "</div>"


def render_plain(text: str, ctx: Ctx, env: dict) -> str:
    """Render reader/notes text without step handling."""
    return render_markdown(text, ctx, env, steps=False)


def pygments_css(style: str = "github-dark") -> str:
    return HtmlFormatter(style=style).get_style_defs(".code")
