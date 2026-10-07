# slidesmith

Slides als code: educatieve presentaties (later ook PDF's en video's) uit tekstbestanden.
Specificatie: `SPEC.md`. Bronformaat: `docs/FORMAAT.md` — lees dit vóór je slides bewerkt.

## Ontwikkelen

```bash
pixi install && pixi run setup     # omgeving + headless Chromium
pixi run test
pixi run slides check voorbeeld
pixi run slides pdf voorbeeld
```

- Python-pakket in `src/slidesmith/`; reveal.js, KaTeX en fonts staan gevendord in `static/vendor/` (offline).
- Pipeline: `parser.py` (bron → model) → `build.py` (model → HTML via `templates/`) met `mdrender.py`, `boxes.py`, `callouts.py`, `diagrams.py`.
- `pdf.py` rendert dezelfde slides in het printthema (`body.theme-print`) via `browser.py` (Playwright); de reader in twee passes voor paginanummers in de inhoudsopgave.
- `video.py`: frames per stap (deck met `?video`), TTS via `tts.py` (cache in `build/.cache/tts`, gesleuteld op tekst+stem+model+instellingen), audiospoor, ffmpeg met tijdbalk via `overlay` (drawbox rekent niet per frame), SRT/VTT, YouTube-hoofdstukken.
- AI-commando's: `ai.py` (client, structured JSON, fallbacks, kosten) + instructies in `src/slidesmith/prompts/*.md`. Volg bij het handmatig vertalen in Claude Code dezelfde regels als `prompts/translate.md` en `glossary.yaml`.
- `translate.py` herschrijft taalblokken in de bron op basis van `LangBlock.end`/`QuizText.end` (eindregel uit de parser) en controleert de structuur vóór het schrijven.
- Draai geen `slides video` zonder `--silent` als de gebruiker daar niet om vraagt: TTS kost tegoed.
- Playwright is aan zijn thread gebonden: in `serve` lopen alle builds op één vaste worker-thread.
- CLI-meldingen zijn Nederlands; code en commentaar Engels.

## Slides bewerken

- NL is de bron. Wijzig je NL-inhoud, werk dan ook het `@en`-blok bij en draai daarna `slides stamp <pad> --id <slide-id>`.
- Houd per slide het aantal `@step`-fragmenten in `@script` gelijk aan het aantal onthulstappen; `slides check` controleert dit.
- Weinig tekst op de slide; uitleg hoort in `@script` (gesproken) of `@reader` (PDF).
- Draai `slides check` na elke wijziging.
