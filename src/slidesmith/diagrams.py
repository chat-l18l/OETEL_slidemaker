"""External diagram renderers (Mermaid, Graphviz, D2), cached by content hash."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from .model import DiagramVisual
from .parser import SourceError

# Dark theme matching theme.css; the print theme (phase 2) gets its own palette.
PALETTE = {"accent": "#F0A030", "text": "#F2F2F2", "bg": "transparent", "line": "#F0A030"}

MERMAID_CONFIG = {
    "theme": "base",
    "htmlLabels": False,
    "flowchart": {"htmlLabels": False, "curve": "basis", "padding": 18},
    "themeVariables": {
        "background": "transparent",
        "primaryColor": PALETTE["accent"],
        "primaryTextColor": "#FFFFFF",
        "primaryBorderColor": PALETTE["accent"],
        "lineColor": PALETTE["line"],
        "secondaryColor": "#3A3F46",
        "tertiaryColor": "#2A2D31",
        "textColor": PALETTE["text"],
        "fontFamily": "Questrial, sans-serif",
        "fontSize": "28px",
    },
}

GRAPHVIZ_DEFAULTS = (
    f'-Gbgcolor=transparent -Gfontname=Questrial -Nfontname=Questrial -Efontname=Questrial '
    f'-Nshape=box -Nstyle=filled -Nfillcolor="{PALETTE["accent"]}" -Ncolor="{PALETTE["accent"]}" '
    f'-Nfontcolor=white -Nfontsize=22 -Ecolor="{PALETTE["line"]}" -Efontcolor="{PALETTE["text"]}" '
    f'-Gfontcolor="{PALETTE["text"]}"'
)

TOOLS = {"mermaid": "mmdc", "graphviz": "dot", "d2": "d2"}


def _run(cmd: list[str], src: str, diagram: DiagramVisual) -> None:
    try:
        r = subprocess.run(cmd, input=src, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise SourceError(f"{cmd[0]} niet gevonden; installeer het voor {diagram.kind}-diagrammen",
                          diagram.loc) from None
    if r.returncode != 0:
        msg = (r.stderr or r.stdout).strip().splitlines()[-5:]
        raise SourceError(f"{diagram.kind} faalde:\n  " + "\n  ".join(msg), diagram.loc)


def render_external(diagram: DiagramVisual, cache_dir: Path) -> str:
    """Render to SVG markup (cached)."""
    tool = TOOLS[diagram.kind]
    key = hashlib.sha256(
        json.dumps([diagram.kind, diagram.source, PALETTE, MERMAID_CONFIG]).encode()
    ).hexdigest()[:16]
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_dir / f"{diagram.kind}-{key}.svg"
    if not out.exists():
        if shutil.which(tool) is None:
            raise SourceError(f"{tool} niet gevonden; installeer het voor {diagram.kind}-diagrammen",
                              diagram.loc)
        tmp = out.with_suffix(".tmp.svg")
        if diagram.kind == "mermaid":
            cfg = cache_dir / "mermaid-config.json"
            cfg.write_text(json.dumps(MERMAID_CONFIG))
            src_file = cache_dir / f"{key}.mmd"
            src_file.write_text(diagram.source)
            _run([tool, "-q", "-i", str(src_file), "-o", str(tmp), "-c", str(cfg), "-b", "transparent"],
                 "", diagram)
            src_file.unlink(missing_ok=True)
        elif diagram.kind == "graphviz":
            import shlex
            _run([tool, "-Tsvg", *shlex.split(GRAPHVIZ_DEFAULTS), "-o", str(tmp)], diagram.source, diagram)
        else:
            _run([tool, "--theme=200", "--pad=0", "-", str(tmp)], diagram.source, diagram)
        tmp.replace(out)
    svg = out.read_text(encoding="utf-8")
    svg = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>", "", svg).strip()
    # let CSS control the size
    svg = re.sub(r'(<svg[^>]*?)\s(width|height)="[^"]*"', r"\1", svg, count=2)
    return f'<div class="ext-diagram">{svg}</div>'
