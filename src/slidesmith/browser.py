"""Headless Chromium (Playwright), shared by Mermaid rendering, PDF export and video frames.

Playwright's sync API is bound to the thread that started it, so there is one browser
per thread, started lazily and closed at exit.
"""

from __future__ import annotations

import atexit
import base64
import threading
from pathlib import Path

from .parser import SourceError

STATIC = Path(__file__).parent / "static"

_local = threading.local()


def _b64(font: str) -> str:
    return base64.b64encode((STATIC / "vendor" / "fonts" / font).read_bytes()).decode()


class _Browser:
    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise SourceError("playwright is niet geïnstalleerd (pixi install, of pip install playwright)") from None
        self._pw = sync_playwright().start()
        try:
            self.browser = self._pw.chromium.launch()
        except Exception as e:  # browser binary missing
            self._pw.stop()
            raise SourceError(
                "Chromium voor Playwright ontbreekt; draai 'pixi run setup' "
                f"(of 'playwright install chromium')\n  {str(e).splitlines()[0]}") from None
        self._mermaid_page = None
        atexit.register(self.close)

    def new_page(self, width: int = 1920, height: int = 1080):
        return self.browser.new_page(viewport={"width": width, "height": height})

    def mermaid_page(self):
        if self._mermaid_page is None:
            page = self.new_page()
            # fonts inline: an about:blank page may not load file:// URLs
            faces = "".join(
                f"@font-face{{font-family:Questrial;src:url(data:font/woff2;base64,{_b64(f)})}}"
                for f in ("questrial-latin-400-normal.woff2", "questrial-latin-ext-400-normal.woff2"))
            page.set_content(f"<!doctype html><html><head><style>{faces}</style></head><body></body></html>")
            page.add_script_tag(path=str(STATIC / "vendor" / "mermaid" / "mermaid.min.js"))
            page.evaluate("document.fonts.load('28px Questrial')")
            self._mermaid_page = page
        return self._mermaid_page

    def close(self) -> None:
        try:
            self.browser.close()
            self._pw.stop()
        except Exception:
            pass


def get() -> _Browser:
    b = getattr(_local, "browser", None)
    if b is None:
        b = _local.browser = _Browser()
    return b


_MERMAID_JS = """
async ([src, cfg]) => {
  mermaid.initialize(Object.assign({startOnLoad: false, securityLevel: 'strict'}, cfg));
  const id = 'm' + Math.random().toString(36).slice(2);
  try {
    const {svg} = await mermaid.render(id, src);
    return {svg};
  } catch (e) {
    document.getElementById('d' + id)?.remove();
    return {error: String(e && e.message || e)};
  }
}
"""


def render_mermaid(source: str, config: dict) -> tuple[str | None, str | None]:
    """Return (svg, error)."""
    r = get().mermaid_page().evaluate(_MERMAID_JS, [source, config])
    return r.get("svg"), r.get("error")
