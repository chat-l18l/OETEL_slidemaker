# slidesmith

Educatieve presentaties als code: tekstbestanden in versiebeheer → presentatie in de browser
en PDF's (in volgende fases ook TTS-video, ondertitels en een OBS-koppeling).

- Geen WYSIWYG: Markdown met `@`-directieven, leesbare diffs, door AI te bewerken
- NL en EN in hetzelfde bestand, met detectie van verouderde vertalingen
- Stapsgewijze onthulling, met een script per stap
- Eigen diagramnotatie (`boxes`) met posities als tekst, plus Mermaid, Graphviz en D2
- Foto's met callouts, code met regelstappen, formules (KaTeX)
- Tijdbalk per hoofdstuk, donker thema, werkt offline
- PDF's in een licht printthema (zuinig met toner): slides, en een reader met inhoudsopgave, kernpunten, quiz, antwoorden en bronnen

## Installeren

Met [pixi](https://pixi.sh) krijg je op Linux, macOS of Windows dezelfde omgeving: Python,
ffmpeg, Graphviz, D2 en Playwright, in de versies uit `pixi.lock`. Alles komt in `.pixi/`; root is niet nodig.

```bash
curl -fsSL https://pixi.sh/install.sh | sh     # eenmalig, als pixi nog niet aanwezig is
git clone <repo> slidesmith && cd slidesmith
pixi install
pixi run setup                                 # headless Chromium voor PDF, video en Mermaid
```

Daarna: `pixi run slides …`, of `pixi shell` en dan gewoon `slides …`.

Zonder pixi kan het ook met `pip install -e .` plus `playwright install chromium-headless-shell`.
Graphviz, D2 en ffmpeg moet je dan zelf installeren.

## Snel starten

```bash
pixi run serve          # = slides serve voorbeeld
```

Open daarna http://127.0.0.1:8000/nl/les01.html. Elke wijziging in `voorbeeld/` herlaadt de pagina.
Toetsen: pijltjes of spatie = volgende stap, `S` = sprekersnotities, `Esc` = overzicht, `F` = volledig scherm.

## Commando's

| commando | functie |
|---|---|
| `slides build [pad] [--lang nl,en]` | HTML bouwen naar `<cursus>/build/` |
| `slides serve [pad] [--port 8000]` | bouwen, serveren, live herladen |
| `slides pdf [pad] [--kind slides,reader]` | PDF's in printthema naar `<cursus>/build/pdf/<taal>/` |
| `slides check [pad] [--strict]` | bron, verwijzingen, stappen en vertalingen controleren |
| `slides stamp [pad] [--id slide]` | vertalingen markeren als bijgewerkt |

Formaat: [docs/FORMAAT.md](docs/FORMAAT.md). Specificatie en fasering: [SPEC.md](SPEC.md).

## Licentie

MIT. Bevat reveal.js (MIT), KaTeX (MIT), Mermaid (MIT), Questrial en JetBrains Mono (SIL OFL).
