# Inventarisatie bestaande tools

Getoetst aan [SPEC.md](SPEC.md). Stand: oktober 2026.

## Kandidaten

| Tool | Type | Stack | Licentie |
|---|---|---|---|
| **reveal.js** | HTML-presentatie-engine | JS-bibliotheek | MIT |
| **Slidev** | Markdown → web-slides | Node / Vue / Vite | MIT |
| **Quarto** (revealjs-output) | publicatiesysteem (Pandoc) | eigen CLI, Python-integratie | MIT |
| **Marp** | Markdown → HTML/PDF/PPTX | Node | MIT |
| **Typst + Touying/Polylux** | slides als PDF | Typst-binary | MIT/Apache |
| **slideSonnet** | Beamer/Marp → video met TTS-stem + ondertitels | Python | MIT (+AGPL dep.) |
| **slidemovie** | Markdown/PPTX → video met TTS-stem | Python | ? |
| Manim / Motion Canvas / Remotion | geanimeerde video als code | Python / TS / React | MIT |

## Featurematrix

Legenda: ✅ aanwezig · 🟡 deels / met plugin of eigen werk · ❌ ontbreekt

| Eis (SPEC §) | reveal.js | Slidev | Quarto | Marp | Typst | slideSonnet |
|---|---|---|---|---|---|---|
| Tekstbron, VCS-vriendelijk (§1) | 🟡 HTML/MD | ✅ | ✅ | ✅ | ✅ | ✅ |
| Eigen `@`-formaat, 1 bestand/hoofdstuk (§10, A) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Progressive disclosure (§2) | ✅ fragments | ✅ v-click | ✅ | 🟡 alleen lijsten | ✅ | 🟡 (Beamer overlays) |
| Disclosure binnen diagram (§3) | 🟡 | 🟡 | 🟡 | ❌ | 🟡 | ❌ |
| Script per onthulstap (§6) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Script / reader / notes gescheiden (§6) | 🟡 alleen notes | 🟡 alleen notes | 🟡 | 🟡 | ❌ | 🟡 |
| NL+EN in één bestand + verouderingshash (§7) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Mesh-achtig donker thema (§8) | ✅ CSS | ✅ CSS | ✅ CSS | ✅ CSS | ✅ | 🟡 Beamer |
| Print-thema voor PDF (§14) | 🟡 eigen CSS | 🟡 | 🟡 | 🟡 | 🟡 | ❌ |
| Reader-PDF: slide + tekst, inhoudsopgave (§14) | ❌ | 🟡 | ✅ (als boek) | ❌ | 🟡 | ❌ |
| Boxes-diagram met posities (§3, A) | ❌ | ❌ | ❌ | ❌ | 🟡 (CeTZ) | ❌ |
| Mermaid / Graphviz / D2 (§3) | 🟡 plugin | ✅ Mermaid/PlantUML | ✅ Mermaid/Graphviz | 🟡 | 🟡 | ❌ |
| Foto-callouts (§9) | ❌ | 🟡 | ❌ | ❌ | 🟡 | ❌ |
| Formules (§9) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tijdbalk per hoofdstuk (§11) | 🟡 simpele balk | 🟡 | 🟡 | ❌ | ❌ | ❌ |
| Presenter view met teleprompter (§12) | ✅ | ✅ | ✅ | 🟡 | ❌ | ❌ |
| Externe aansturing (OBS Browser Source) (§12) | ✅ postMessage-API | 🟡 | ✅ (reveal) | ❌ | ❌ | ❌ |
| OBS-websocket: opname + klik-tijdstempels (§12) | ❌ | 🟡 eigen recorder | ❌ | ❌ | ❌ | ❌ |
| TTS-video, gekloonde stem ElevenLabs (§4) | ❌ | ❌ | ❌ | ❌ | ❌ | 🟡 andere TTS-engines |
| Audio-cache per fragment (§5) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| Ondertitels SRT/VTT (§15) | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| YouTube-hoofdstukken (§11) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Key points + quiz (§15) | ❌ | 🟡 | 🟡 | ❌ | ❌ | ❌ |
| AI-commando's (§13) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Web-versie (§15) | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| Python als hoofdstack (§5) | ❌ | ❌ | 🟡 | ❌ | ❌ | ✅ |

## Conclusie

**Geen enkele tool dekt de combinatie.** Wat bestaat valt in twee groepen:

1. **Presentatie-engines** (reveal.js, Slidev, Quarto, Marp): goed in slides tonen, stappen en presenter view. Zwak in video, TTS, meertaligheid, reader-PDF en OBS.
2. **Slides→video-tools** (slideSonnet, slidemovie): doen de TTS-video. Ze gaan uit van een *bestaand* slideformaat (Beamer/Marp/PPTX) en kennen geen live modus, meertaligheid of reader.

Het onderscheidende deel van de specificatie, namelijk het `@`-formaat met tekstlagen per stap, NL/EN met hash, key points en quiz, en de boxes-DSL, is in elk scenario **eigen werk**. Een framework als Slidev of Quarto aanpassen aan dit formaat kost meer dan het oplevert, en dan zit je ook nog vast aan Node/Vue of Pandoc-filters.

## Advies: zelf bouwen in Python, met reveal.js als render-engine

```
bron (.md met @-directieven)
   │  Python-parser
   ▼
deck-model (JSON)  ──►  TTS (ElevenLabs, cache)  ──►  audio + timings
   │
   ├─► HTML (reveal.js + eigen thema/plugins) ─► live / OBS Browser Source / web-versie
   ├─► Playwright (headless Chromium):
   │      ├─ print-thema → PDF slides / PDF reader
   │      └─ screenshot per stap → ffmpeg + audio → mp4 + SRT/VTT + YouTube-hoofdstukken
   └─► Presenter-server (Python, websocket) ◄─► presenter view, OBS-websocket
```

**Zelf bouwen (Python):** parser en validatie van het formaat, deck-model, CLI (`slides build/serve/video/translate/review/draft/quiz/image`), boxes-DSL → SVG, callouts → SVG, TTS-adapter + cache, video-pipeline (ffmpeg), ondertitels, presenter-server + OBS-koppeling (`obsws-python`), AI-commando's (Anthropic / OpenAI / x.ai / ElevenLabs SDK's).

**Hergebruiken:**
- **reveal.js** (MIT): fragments, presenter view, auto-slide, KaTeX, code-highlighting met regelstappen, postMessage-API voor externe aansturing, print-to-PDF. Volwassen en stabiel, en we gebruiken het als "dom" render-doel, niet als authoring-formaat.
- **Playwright** (Python): exact 1920×1080 renderen, screenshots per stap, PDF's.
- **ffmpeg**, **Mermaid-CLI**, **D2**, **Graphviz** als externe renderers.
- **obsws-python** voor OBS.
- Ideeën uit **slideSonnet**: uitspraakcorrecties, tempo per fragment, gedeelde audio-pool, bevestiging vóór betaalde synthese.

**Alternatief overwogen:** een eigen JS-runtime in plaats van reveal.js. Die is kleiner en geeft volledige controle, maar dan moet je fragments, presenter view, schaling en PDF-print zelf schrijven. Pas zinvol als reveal.js gaat knellen. Het deck-model als tussenlaag houdt die overstap goedkoop.

## Bronnen

- [slideSonnet](https://github.com/avivz/slideSonnet) · [SlideSonnet demo](https://www.youtube.com/watch?v=u6yOFujj_f0)
- [slidemovie (PyPI)](https://pypi.org/project/slidemovie/0.8.1/)
- [PPTX-Narrator](https://zenodo.org/records/23008488)
- [slide-stream](https://github.com/michael-borck/slide-stream)
- [Slidev vs Marp vs reveal.js 2026](https://www.pkgpulse.com/guides/slidev-vs-marp-vs-revealjs-code-first-presentations-2026)
- [Marp vs reveal.js vergelijking](https://dev.classmethod.jp/en/articles/marp-vs-revealjs-markdown-presentation-tools-comparison/)
- [obsws-python](https://tessl.io/registry/tessl/pypi-obsws-python) · [OBSStamper](https://awesome.ecosyste.ms/projects/github.com%2Fpoeschl%2Fobsstamper)
