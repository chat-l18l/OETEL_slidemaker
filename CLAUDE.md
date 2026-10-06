# slidesmith

Slides als code: educatieve presentaties (later ook PDF's en video's) uit tekstbestanden.
Specificatie: `SPEC.md`. Bronformaat: `docs/FORMAAT.md` — lees dit vóór je slides bewerkt.

## Ontwikkelen

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
.venv/bin/slides check voorbeeld
.venv/bin/slides serve voorbeeld
```

- Python-pakket in `src/slidesmith/`; reveal.js, KaTeX en fonts staan gevendord in `static/vendor/` (offline).
- Pipeline: `parser.py` (bron → model) → `build.py` (model → HTML via `templates/`) met `mdrender.py`, `boxes.py`, `callouts.py`, `diagrams.py`.
- CLI-meldingen zijn Nederlands; code en commentaar Engels.

## Slides bewerken

- NL is de bron. Wijzig je NL-inhoud, werk dan ook het `@en`-blok bij en draai daarna `slides stamp <pad> --id <slide-id>`.
- Houd per slide het aantal `@step`-fragmenten in `@script` gelijk aan het aantal onthulstappen; `slides check` controleert dit.
- Weinig tekst op de slide; uitleg hoort in `@script` (gesproken) of `@reader` (PDF).
- Draai `slides check` na elke wijziging.
