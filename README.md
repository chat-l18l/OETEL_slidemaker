# slidesmith

Educatieve presentaties als code: tekstbestanden in versiebeheer → presentatie in de browser
(en in volgende fases: PDF's, TTS-video, ondertitels en een OBS-koppeling).

- Geen WYSIWYG: Markdown met `@`-directieven, leesbare diffs, door AI te bewerken
- NL en EN in hetzelfde bestand, met detectie van verouderde vertalingen
- Stapsgewijze onthulling, met een script per stap
- Eigen diagramnotatie (`boxes`) met posities als tekst, plus Mermaid, Graphviz en D2
- Foto's met callouts, code met regelstappen, formules (KaTeX)
- Tijdbalk per hoofdstuk, donker thema, werkt offline

## Snel starten

```bash
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/slides serve voorbeeld
```

Open daarna http://127.0.0.1:8000/nl/les01.html. Elke wijziging in `voorbeeld/` herlaadt de pagina.
Toetsen: pijltjes of spatie = volgende stap, `S` = sprekersnotities, `Esc` = overzicht, `F` = volledig scherm.

## Commando's

| commando | functie |
|---|---|
| `slides build [pad] [--lang nl,en]` | HTML bouwen naar `<cursus>/build/` |
| `slides serve [pad] [--port 8000]` | bouwen, serveren, live herladen |
| `slides check [pad] [--strict]` | bron, verwijzingen, stappen en vertalingen controleren |
| `slides stamp [pad] [--id slide]` | vertalingen markeren als bijgewerkt |

Formaat: [docs/FORMAAT.md](docs/FORMAAT.md). Specificatie en fasering: [SPEC.md](SPEC.md).

## Licentie

MIT. Bevat reveal.js (MIT), KaTeX (MIT), Questrial en JetBrains Mono (SIL OFL).
