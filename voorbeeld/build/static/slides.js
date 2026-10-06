/* slidesmith runtime: reveal.js setup, chapter time bar, code line steps, live reload. */
(function () {
  "use strict";
  const D = window.DECK;
  // ?video: frames for the rendered video (no transitions; ffmpeg draws the time bar)
  const VIDEO = new URLSearchParams(location.search).has("video");
  if (VIDEO) document.body.classList.add("video-mode");

  Reveal.initialize({
    width: 1920,
    height: 1080,
    margin: 0,
    minScale: 0.05,
    maxScale: 4,
    center: false,
    hash: true,
    fragmentInURL: true,
    controls: false,
    progress: false,
    slideNumber: false,
    transition: VIDEO ? "none" : "fade",
    transitionSpeed: "fast",
    backgroundTransition: "none",
    plugins: [RevealNotes],
  });

  // ---- time bar ------------------------------------------------------------

  const bar = VIDEO ? null : document.getElementById("timebar");
  const segs = [];
  if (bar && D.total > 0) {
    for (const ch of D.chapters) {
      const el = document.createElement("div");
      el.className = "seg";
      el.style.flex = `${Math.max(ch.dur, 0.001)} 1 0`;
      el.dataset.title = ch.title;
      el.innerHTML = '<div class="fill"></div>';
      bar.appendChild(el);
      segs.push(el);
    }
  }

  function visibleSteps(slide) {
    const idx = new Set();
    slide.querySelectorAll(".fragment.visible").forEach((f) => idx.add(f.dataset.fragmentIndex));
    return idx.size;
  }

  function updateTimebar(slide, h) {
    if (!segs.length) return;
    const info = D.slides[h];
    if (!info) return;
    const k = visibleSteps(slide);
    let t = info.start;
    for (let i = 0; i < k && i < info.steps.length; i++) t += info.steps[i];
    D.chapters.forEach((ch, i) => {
      const fill = segs[i].querySelector(".fill");
      const p = ch.dur > 0 ? (t - ch.start) / ch.dur : 0;
      const pct = Math.min(1, Math.max(0, p)) * 100;
      fill.style.width = `${t >= ch.start + ch.dur ? 100 : pct}%`;
    });
  }

  // ---- code line highlighting per step ------------------------------------------

  function updateCode(slide) {
    slide.querySelectorAll(".code-wrap").forEach((wrap) => {
      const shown = wrap.querySelectorAll(".code-step.visible");
      const last = shown[shown.length - 1];
      const prefix = wrap.dataset.prefix;
      wrap.querySelectorAll("pre span[id]").forEach((s) => s.classList.remove("hl"));
      wrap.classList.toggle("focus", !!last);
      if (!last) return;
      for (const n of last.dataset.lines.split(",")) {
        const line = wrap.querySelector(`[id="${prefix}-${n}"]`);
        if (line) line.classList.add("hl");
      }
    });
  }

  function update() {
    const slide = Reveal.getCurrentSlide();
    if (!slide) return;
    updateTimebar(slide, Reveal.getIndices().h);
    updateCode(slide);
  }

  Reveal.on("ready", () => {
    if (window.renderMathInElement) {
      renderMathInElement(document.querySelector(".reveal .slides"), {
        delimiters: [
          { left: "\\[", right: "\\]", display: true },
          { left: "\\(", right: "\\)", display: false },
        ],
        throwOnError: false,
      });
    }
    update();
  });
  ["slidechanged", "fragmentshown", "fragmenthidden"].forEach((e) => Reveal.on(e, update));

  // ---- live reload (slides serve) ---------------------------------------------

  if (D.live) {
    const box = document.getElementById("build-error");
    const connect = () => {
      const ws = new WebSocket(`ws://${location.hostname}:${D.live}`);
      ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data);
        if (msg.type === "reload") location.reload();
        if (msg.type === "error") { box.textContent = msg.text; box.hidden = false; }
        if (msg.type === "ok") box.hidden = true;
      };
      ws.onclose = () => setTimeout(connect, 1000);
    };
    connect();
  }

  window.SLIDESMITH = { update };
})();
