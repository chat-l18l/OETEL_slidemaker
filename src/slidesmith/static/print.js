/* slidesmith print runtime: render math, check text contrast, then signal ready. */
(function () {
  "use strict";

  function parse(c) {
    const m = c.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[ ,/]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  }

  function lum({ r, g, b }) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
  }

  function background(el) {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.backgroundImage && cs.backgroundImage !== "none") return null; // unknown
      const bg = parse(cs.backgroundColor);
      if (bg && bg.a > 0.5) return bg;
    }
    return { r: 255, g: 255, b: 255, a: 1 }; // paper
  }

  function checkContrast() {
    const warnings = [];
    const seen = new Set();
    document.querySelectorAll("body *").forEach((el) => {
      if (el.closest("svg, .katex, script, style")) return;
      const own = Array.from(el.childNodes).some((n) => n.nodeType === 3 && n.textContent.trim());
      if (!own || !el.getClientRects().length) return;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none") return;
      const fg = parse(cs.color);
      const bg = background(el);
      if (!fg || !bg) return;
      const text = el.textContent.trim().slice(0, 40);
      const where = el.closest("[data-slide-id]")?.dataset.slideId || "reader";
      if (fg.a < 0.1) {
        warnings.push(`${where}: onzichtbare tekst "${text}"`);
        return;
      }
      const [l1, l2] = [lum(fg), lum(bg)].sort((a, b) => b - a);
      const ratio = (l1 + 0.05) / (l2 + 0.05);
      const key = where + text;
      if (ratio < 3 && !seen.has(key)) {
        seen.add(key);
        warnings.push(`${where}: weinig contrast (${ratio.toFixed(1)}:1) bij "${text}"`);
      }
    });
    return warnings;
  }

  async function run() {
    if (window.renderMathInElement) {
      renderMathInElement(document.body, {
        delimiters: [
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    }
    await document.fonts.ready;
    await Promise.all(Array.from(document.images).map((img) =>
      img.complete ? null : new Promise((r) => { img.onload = img.onerror = r; })));
    window.__warnings = checkContrast();
    window.__ready = true;
  }

  run();
})();
