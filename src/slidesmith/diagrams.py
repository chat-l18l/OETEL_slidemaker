"""Diagram-as-code renderers (Mermaid, Graphviz, D2), cached by content hash.

Each diagram is rendered per theme: the dark palette for screen/video, the print
palette (light fills, dark text, little ink) for PDF.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path

from .model import DiagramVisual
from .parser import SourceError

PALETTES = {
    "dark": {"fill": "#F0A030", "stroke": "#F0A030", "node_text": "#FFFFFF",
             "line": "#F0A030", "text": "#F2F2F2", "secondary": "#3A3F46", "tertiary": "#2A2D31"},
    "print": {"fill": "#FCE3BD", "stroke": "#D88A1C", "node_text": "#1A1A1A",
              "line": "#C77A12", "text": "#1A1A1A", "secondary": "#F3F3F3", "tertiary": "#FFFFFF"},
}

TOOLS = {"mermaid": None, "graphviz": "dot", "d2": "d2"}


def mermaid_config(theme: str) -> dict:
    p = PALETTES[theme]
    return {
        "theme": "base",
        "htmlLabels": False,
        "flowchart": {"htmlLabels": False, "curve": "basis", "padding": 18},
        "themeVariables": {
            "background": "transparent",
            "primaryColor": p["fill"],
            "primaryTextColor": p["node_text"],
            "primaryBorderColor": p["stroke"],
            "lineColor": p["line"],
            "secondaryColor": p["secondary"],
            "tertiaryColor": p["tertiary"],
            "textColor": p["text"],
            "edgeLabelBackground": "transparent",
            "fontFamily": "Questrial, sans-serif",
            "fontSize": "28px",
        },
    }


def graphviz_args(theme: str) -> list[str]:
    p = PALETTES[theme]
    return shlex.split(
        f'-Gbgcolor=transparent -Gfontname=Questrial -Nfontname=Questrial -Efontname=Questrial '
        f'-Nshape=box -Nstyle=filled -Nfillcolor="{p["fill"]}" -Ncolor="{p["stroke"]}" '
        f'-Nfontcolor="{p["node_text"]}" -Nfontsize=22 -Ecolor="{p["line"]}" '
        f'-Efontcolor="{p["text"]}" -Gfontcolor="{p["text"]}"')


def _run(cmd: list[str], src: str, diagram: DiagramVisual) -> None:
    try:
        r = subprocess.run(cmd, input=src, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise SourceError(f"{cmd[0]} niet gevonden; installeer het voor {diagram.kind}-diagrammen",
                          diagram.loc) from None
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()[-5:]
        raise SourceError(f"{diagram.kind} faalde:\n  " + "\n  ".join(msg), diagram.loc)


def _render(diagram: DiagramVisual, theme: str, out: Path) -> None:
    tmp = out.with_suffix(".tmp.svg")
    if diagram.kind == "mermaid":
        from . import browser

        svg, error = browser.render_mermaid(diagram.source, mermaid_config(theme))
        if error:
            raise SourceError(f"mermaid: {error}", diagram.loc)
        tmp.write_text(svg, encoding="utf-8")
    else:
        tool = TOOLS[diagram.kind]
        if shutil.which(tool) is None:
            raise SourceError(f"{tool} niet gevonden; installeer het voor {diagram.kind}-diagrammen "
                              "(zit in de pixi-omgeving)", diagram.loc)
        if diagram.kind == "graphviz":
            _run([tool, "-Tsvg", *graphviz_args(theme), "-o", str(tmp)], diagram.source, diagram)
        else:
            d2_theme = "200" if theme == "dark" else "0"
            _run([tool, f"--theme={d2_theme}", "--pad=0", "-", str(tmp)], diagram.source, diagram)
    tmp.replace(out)


def render_external(diagram: DiagramVisual, cache_dir: Path, theme: str = "dark") -> str:
    """Render to inline SVG markup (cached per source + theme)."""
    key = hashlib.sha256(json.dumps(
        [diagram.kind, diagram.source, theme, PALETTES[theme], mermaid_config(theme)]
    ).encode()).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{diagram.kind}-{theme}-{key}.svg"
    if not out.exists():
        _render(diagram, theme, out)
    svg = out.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", svg, flags=re.S).strip()
    # let CSS control the size
    svg = re.sub(r'(<svg[^>]*?)\s(width|height)="[^"]*"', r"\1", svg, count=2)
    svg = re.sub(r'(<svg[^>]*?)\sstyle="max-width:[^"]*"', r"\1", svg, count=1)
    return f'<div class="ext-diagram">{svg}</div>'
