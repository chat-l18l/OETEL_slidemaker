# Slide Creator — Specificatie (concept)

Status: inventarisatie van eisen. Nog geen keuze voor bestaande tool vs. zelf bouwen.

## 1. Uitgangspunten

- Gebruiker is programmeur/techneut; tooling moet daarbij passen.
- **Geen WYSIWYG**, geen slepen met muis. Alles via tekstbestanden.
- Bron moet goed werken met **git / hg / svn**: platte tekst, leesbare diffs, mergebaar.
- **Claude (AI) moet de bronbestanden direct kunnen editen**: voorspelbare, goed gedocumenteerde syntax.
- Doel: **educatieve slides** met tekst en plaatjes.
- Visuele stijl: rustig/technisch, geïnspireerd op Andreas Spiess.

## 2. Bronformaat

- Markdown-achtig tekstformaat.
- Per slide: inhoud, **sprekernotities**, **reader-tekst** (voor hand-out/TTS).
- **Progressive disclosure**: stapsgewijs onthullen van elementen (ook binnen diagrammen).
- **Timing** per slide/stap (voor automatische volgende stap en video).

## 3. Graphics

- Rasterplaatjes: jpg, png. Vector: svg. Invoegen via bestandsverwijzing.
- **Diagram-as-code** via fenced code blocks, gerenderd naar SVG bij build:
  - Mermaid (flowcharts, sequence)
  - D2 (architectuur, mooiere layout)
  - Graphviz (grafen, state machines)
  - optioneel: PlantUML, WaveDrom (timing diagrams)
- Syntax highlighting voor broncode.

## 4. Uitvoer

| Output | Omschrijving |
|---|---|
| Live presentatie | In browser; automatische volgende stap; optionele **tijdbalk onderin** |
| PDF – slides | Alleen slides |
| PDF – reader | Slides + reader-tekst (hand-out) |
| Video – concept | Automatisch gerenderde mp4: slides + timing + **TTS van reader-tekst** |
| Video – definitief | Live presentatie opgenomen door gebruiker (bv. OBS), eigen stem |

### Video-workflow
1. Concept: tool rendert mp4 met TTS-stem → snel reviewen van flow en timing.
2. Definitief: gebruiker presenteert live (browser) en neemt zelf op.

## 5. Technische omgeving

- Platform: **Linux / WSL2**.
- Voorkeur taal/stack: **Python** (CLI, build pipeline). Frontend (browser-presentatie) is onvermijdelijk HTML/JS, maar tooling eromheen in Python.
- Build: CLI + watch-mode met live reload (aanname, te bevestigen).
- Cloud toegestaan; beschikbare abonnementen:
  - **ElevenLabs** — primaire kandidaat voor TTS (kwaliteit, Nederlands, voice cloning)
  - **OpenAI** — alternatieve/goedkopere TTS; evt. beeldgeneratie
  - **Anthropic** — Claude voor schrijven/reviewen van slides en reader-tekst
  - **x.ai** — te verkennen (TTS/beeld)
- **Uitspraak-lexicon** per cursus (vaktermen, afkortingen als "ESP32", "FSD"), per taal; vertaald naar ElevenLabs pronunciation dictionaries / inline correcties.
- TTS-provider moet verwisselbaar zijn (adapter), met caching van audio per tekstfragment (hash) zodat alleen gewijzigde slides opnieuw worden ingesproken.

## 6. Taal, stem en tekstlagen

- Talen: **Nederlands en Engels**; één bron levert per taal eigen PDF's en video's.
- Concept-video met **eigen gekloonde stem** (ElevenLabs voice clone).
- Per slide drie tekstlagen, gescheiden:

| Laag | Doel | Gebruikt in |
|---|---|---|
| **Slide-inhoud** | wat op het scherm staat | presentatie, PDF, video |
| **Script** | gesproken tekst | TTS concept-video; teleprompter/presenter view bij live opname |
| **Reader** | uitgebreidere uitleg, verwijzingen | PDF-reader / hand-out |

- (Ontwerpvoorstel) Script is opgedeeld **per onthulstap**: de duur van de TTS-audio per stap bepaalt automatisch de timing van de progressive disclosure in de concept-video. Handmatige timing kan dit overrulen.
- (Ontwerpvoorstel) Bij live opname toont de presenter view het script als teleprompter.

## 7. Meertaligheid

- **Brontaal: Nederlands.** Engels wordt door **Claude vertaald**, gebruiker reviewt.
- **Beide talen in hetzelfde bestand**, per slide naast elkaar (diff toont direct ontbrekende/verouderde vertaling).
- **Verouderingsdetectie**: elke vertaling bewaart een hash van de NL-brontekst waarop ze gebaseerd is. Build geeft een **waarschuwing** als NL gewijzigd is sinds de vertaling.
- Vertaal-commando in de CLI (bv. `slides translate`) dat alleen ontbrekende/verouderde fragmenten via de Anthropic API vertaalt en de hash bijwerkt.
- (Aanname) Plaatjes/diagrammen kunnen optioneel een variant per taal hebben; zonder variant wordt de NL-versie gebruikt. Diagram-labels in diagram-as-code kunnen per taal worden opgegeven.

## 8. Visuele stijl (referentie: Andreas Spiess, "Ishikawa Circle")

Waargenomen kenmerken van de referentieslide:
- **Donkere achtergrond**: antraciet met fijne punt/carbon-textuur en lichte vignettering (midden iets lichter).
- **Accentkleur oranje/amber** (~`#F0A030`) voor gevulde blokken, witte tekst erin.
- **Pijlen** in dezelfde accentkleur, dun, met kleine pijlpunt.
- **Titel** wit, dun geometrisch sans-serif (Century Gothic-achtig), groot, rechtsboven — niet de standaard gecentreerde titelbalk.
- **Minimaal tekst**: alleen kernwoorden, geen zinnen.
- Teller/timer linksboven ("1.00") — mogelijk tijdsindicatie.
- Diagram is **handmatig gepositioneerd** (cirkel van stappen), niet auto-layout.

Tweede referentieslide ("The AI agent can:"):
- Zelfde achtergrond. Titel **linksboven, HOOFDLETTERS**, dun geometrisch font, licht grijs-wit.
- Opsomming met eenvoudige bullets, dun font, ruime regelafstand, weinig woorden per regel.
- Afsluitende **conclusieregel** ("→ Workbench is an automated test lab"): groter, helderder wit, met pijl — de kernboodschap van de slide.
- Ruime marges, veel lege ruimte.
- Het geheel lijkt sterk op het PowerPoint-thema "Mesh" (Century Gothic + donkere textuur); als open alternatief font: bv. *Questrial*, *Didact Gothic* of *Poppins Light*.

Consequenties voor het ontwerp:
- Layout **"bullets + takeaway"**: opsomming gevolgd door een uitgelichte conclusieregel (typisch als laatste onthulstap).
- Thema = CSS-variabelen (achtergrond, accent, font) → gemakkelijk eigen huisstijl.
- Diagrammen moeten in deze stijl renderen (Mermaid/D2 theming, of eigen renderer).
- Er is behoefte aan **diagrammen met tekstueel opgegeven posities** (grid/coördinaten) naast auto-layout. Kandidaat: eigen eenvoudige "boxes & arrows"-DSL (YAML/tekst, grid-coördinaten) → SVG, met **stapsgewijze onthulling per blok/pijl**.

## 9. Formaat, huisstijl en layouts

- Formaat: **16:9, 1920×1080** (vaste canvas, geschaald naar scherm).
- Thema: **alleen donker** (Mesh-achtig, zie §8). Accentkleur blijft **oranje**.
- **Logo** in een hoek: optioneel, per deck in/uit te schakelen (en per slide te onderdrukken).
- **Geen video-clips** in slides.
- **Scherm/video: donker thema** (rust voor de ogen op TV/beamer).
- **PDF: print-variant** van het thema (zie §14): wit papier, donkere tekst, oranje accent behouden, plaatjes in kleur. Geen donkere vlakken → zuinig met toner/inkt. Wordt automatisch afgeleid van hetzelfde thema (CSS `@media print`-achtige variant), geen apart ontwerpwerk per slide.

### Layouts

| Layout | Omschrijving |
|---|---|
| `title` | titel / hoofdstuk-opener |
| `bullets` | opsomming, optioneel met **takeaway**-regel (→ conclusie) |
| `image` | groot beeld, optioneel kort onderschrift |
| `two-col` | twee kolommen: tekst+beeld, beeld+beeld, tekst+tekst |
| `code` | code met syntax highlighting; regels stapsgewijs oplichten |
| `diagram` | diagram-as-code (Mermaid / D2 / Graphviz / eigen boxes&arrows-DSL) |
| `quote` | één kernboodschap groot in beeld |
| `table` | vergelijking / tabel |
| `formula` | formules (LaTeX via KaTeX/MathJax), ook inline in andere layouts |
| `callouts` | **foto met callouts**: pijlen, cirkels, kaders en labels op een foto, posities als tekst (relatieve coördinaten), stapsgewijs onthulbaar |

## 10. Projectstructuur

- Hiërarchie: **cursus → les → hoofdstuk → slide**.
- **Eén bronbestand per hoofdstuk** (bevat alle slides van dat hoofdstuk, beide talen).
- **Hergebruik**: slides en diagrammen kunnen gedeeld worden tussen lessen/cursussen (include-mechanisme).
- **Assets in de repo** (gewone bestanden; git-lfs optioneel voor grote bestanden).
- Build-output (PDF, mp4, HTML, TTS-cache) **niet** in versiebeheer (`build/` in ignore).

Voorstel mappenstructuur:

```
mijn-cursus/
  course.yaml              # titel, talen, thema, stem-id, logo, volgorde lessen
  shared/
    slides/                # herbruikbare slides (intro, outro, ...)
    diagrams/              # herbruikbare diagrammen
    assets/                # logo, gedeelde foto's
  lessen/
    01-introductie/
      lesson.yaml          # titel, volgorde hoofdstukken
      01-waarom.md         # hoofdstuk = bronbestand met slides
      02-opzet.md
      assets/              # plaatjes specifiek voor deze les
    02-.../
  build/                   # gegenereerd, niet in VCS
```

- Een slide kan verwijzen naar `@shared/slides/intro.md` of `@shared/diagrams/x.d2`.
- Build per niveau: hele cursus, één les of één hoofdstuk (bv. `slides build lessen/01-introductie --lang en --pdf reader`).

## 11. Tijdbalk, navigatie en hoofdstukken

- **Tijdbalk onderin, gesegmenteerd per hoofdstuk** (à la YouTube-chapters), **zichtbaar voor iedereen** (publiek, PDF niet, video wel). Per deck uit te schakelen.
  - Segmentbreedte ∝ (geschatte) duur van het hoofdstuk; voortgangsindicator binnen het actieve segment.
  - Duur komt uit TTS-audio (concept) of uit opgegeven/gemeten tijden.
- (Aanname) Optioneel **tijdsbudget** per hoofdstuk; voor/achter-indicatie alleen in de presenter view.
- **Live presenteren: altijd handmatig doorklikken** (toetsenbord, presenter-clicker). Automatisch doorgaan alleen in de gerenderde video.
- **YouTube-hoofdstuk-tijdstempels** automatisch gegenereerd bij video-export (`00:00 Intro` …), per taal.

## 12. Live opname (definitieve video)

- Opname met **OBS**, op **één scherm**, **webcam in een hoek**.
- **Opname per hoofdstuk** (losse takes); de tool plakt de takes daarna aan elkaar (ffmpeg) tot één video per les.
- Layout houdt rekening met de webcam: een configureerbare **webcam-zone** (hoek + grootte) wordt vrijgehouden; de build waarschuwt als inhoud in die zone valt.

Ontwerpvoorstel voor één scherm:
- Slides draaien als **OBS Browser Source** (onzichtbaar renderen in OBS, exact 1920×1080, geen browser-chrome).
- Op het scherm staat de **presenter view** (normaal browservenster): huidige/volgende stap, script als teleprompter, tijdsbudget. Klikken hier stuurt de slides in OBS aan via een lokale websocket-server.
- (Aanname) **OBS-websocket-koppeling**:
  - opname starten/stoppen per hoofdstuk vanuit de presenter view;
  - **tijdstempel van elke klik** vastleggen → correcte YouTube-hoofdstukken en een slide/tijd-index voor de echte opname;
  - automatisch scènewissel per layout: optioneel, latere versie.

## 13. AI-ondersteuning

Twee routes, met **dezelfde onderliggende instructies/prompts** (één bron van waarheid in de repo):
1. **Claude Code** in de repo: een `CLAUDE.md` + skills die het bronformaat, de layouts en de stijlregels beschrijven, zodat Claude correct kan editen.
2. **CLI-commando's** die de Anthropic API aanroepen.

| Commando | Functie |
|---|---|
| `slides draft` | outline/steekwoorden → complete slides met script en reader-tekst |
| `slides assist` | gerichte hulp op een slide (inkorten, diagram maken, herformuleren) |
| `slides review` | controle: te veel tekst per slide, script ↔ slide-aansluiting, consistentie, spelling/terminologie |
| `slides translate` | NL → EN voor ontbrekende/verouderde fragmenten (zie §7) |
| `slides image` | illustratie genereren (OpenAI / x.ai), opgeslagen als asset in de repo |

- AI-wijzigingen gaan **altijd als gewone tekstwijziging** naar de bronbestanden → controleerbaar via diff, terug te draaien via VCS.
- Review-output als rapport (en optioneel als commentaar in de bron), niet als stille wijziging.
- **Gegenereerde plaatjes**: prompt + model + seed worden in een sidecar-bestand naast het plaatje opgeslagen (reproduceerbaar, herkenbaar als AI-gegenereerd). Stijl-prompt sluit aan bij het thema (donker, oranje accent).
- Terminologielijst per cursus (`glossary.yaml`) voor consistente vertalingen en review.

## 14. PDF-uitvoer

- **Print-thema** voor alle PDF's: witte achtergrond, zwarte/donkergrijze tekst, oranje accent (eventueel iets donkerder voor contrast op wit), plaatjes en foto's in kleur. Geen donkere achtergronden of witte tekst.
  - Diagrammen worden met het print-palet opnieuw gerenderd (niet de donkere SVG hergebruiken).
  - Foto's met eigen donkere achtergrond blijven ongewijzigd.
  - Build controleert contrast: waarschuwing bij lichte tekst op lichte achtergrond.
- Elke slide toont in de PDF de **eindstand** (alle onthulstappen zichtbaar).
- **Reader-PDF**: per slide de slide bovenaan, de reader-tekst eronder (A4 staand).
- **Slides-PDF**: één slide per pagina (A4 liggend/16:9), print-thema.
- Extra's in beide PDF's (configureerbaar):
  - titelpagina (cursus/les, versie, datum, auteur)
  - inhoudsopgave (les → hoofdstuk → slide)
  - paginanummers
  - klikbare links
  - bronnenlijst (verzameld uit verwijzingen in reader-tekst)
- (Voorstel) Versie-info uit VCS op de titelpagina (commit-hash/tag + datum), zodat een geprinte versie herleidbaar is.

## 15. Publicatie en didactiek

- **Ondertitels (SRT + VTT) per taal**:
  - TTS-video: exact getimed vanuit de audio per scriptfragment.
  - Live opname: getimed via de klik-tijdstempels (§12), optioneel fijn uitgelijnd met forced alignment / speech-to-text (bv. Whisper / ElevenLabs STT).
  - Ondertitel in andere taal dan de gesproken taal mogelijk (NL video + EN ondertitels).
- **Web-versie**: statische HTML-site per cursus (zelf doorklikken, beide talen, zonder server-afhankelijkheden); te hosten op GitHub Pages of eigen server.
- **Geen LMS-koppeling** (geen SCORM). (Open: YouTube-upload via API — vooralsnog niet.)
- **Key points**: per hoofdstuk expliciet benoemde kernpunten in de bron. Slides verwijzen ernaar. Ze worden gebruikt voor:
  - samenvattingsslide aan het eind van een hoofdstuk/les (automatisch te genereren);
  - **quizvragen** die de key points herhalen;
  - review (dekt elke slide een key point? wordt elk key point behandeld?).
- **Quiz** per hoofdstuk in de bron (meerkeuze, open vraag, waar/onwaar), gekoppeld aan key points:
  - web-versie: interactief, met directe feedback;
  - reader-PDF: vragen aan het eind van het hoofdstuk, antwoorden in een bijlage;
  - video: optionele quizslide ("pauzeer de video en denk na") gevolgd door het antwoord.
  - `slides draft --quiz` laat Claude vragen voorstellen op basis van de key points.

## 16. Randvoorwaarden en fasering

- Licentie: **MIT** (open source).
- Geen budgetgrens voor API-kosten (wel caching om onnodige kosten te vermijden).
- Geen deadline.

Fasering:
1. Bronformaat → live presentatie in browser (thema, stappen, tijdbalk)
2. PDF's (slides + reader, print-thema)
3. TTS-conceptvideo + ondertitels + YouTube-tijdstempels
4. AI-commando's: translate, review, draft, quiz, image
5. OBS-koppeling + presenter view (live opname per hoofdstuk, samenvoegen)
6. Web-versie + interactieve quiz

## 17. Open vragen

- ~~Keuze bouwen vs. bestaand~~ → **akkoord**: eigen Python-tool met reveal.js als render-engine (zie [INVENTARISATIE.md](INVENTARISATIE.md)).
- Fase 1 gereed (live presentatie, thema, stappen, tijdbalk, `serve`/`check`/`stamp`).

- ~~Syntax bronformaat~~ → **akkoord** op v0 (Bijlage A): `@`-directieven, NL/EN per slide onder elkaar, eigen `boxes`-diagramnotatie.

---

## Bijlage A — Voorstel bronformaat v0

Principes:
- Gewone Markdown voor inhoud; **directieven op een eigen regel, beginnend met `@`** voor structuur. Makkelijk te parsen, makkelijk te lezen, kleine diffs.
- Per slide eerst NL, daaronder EN. EN-blok onthoudt een hash van de NL-bron (`src=`), ingevuld door `slides translate`.
- Elk lijst-item / elk element met `{step}` is een onthulstap. Script-fragmenten worden met `@step` gescheiden: fragment *n* wordt gesproken bij stap *n*.

```markdown
---
id: h01-waarom
title:
  nl: Waarom een testlab?
  en: Why a test lab?
keypoints:
  agent-loop:
    nl: Een AI-agent kan de volledige test-loop zelfstandig doorlopen.
    en: An AI agent can run the full test loop on its own.
  cycle:
    nl: Ontwikkelen is een cyclus, geen rechte lijn.
    en: Development is a cycle, not a straight line.
---

@slide agent-can layout=bullets keypoints=agent-loop

@nl
## De AI-agent kan:
- Firmware flashen
- De seriële log volgen
- Tests draaien
- De resultaten valideren
- Problemen in de code oplossen

=> Workbench is een geautomatiseerd testlab

@script
Wat kan zo'n agent nu eigenlijk allemaal?
@step
Om te beginnen flasht hij zelf de firmware.
@step
Daarna leest hij mee op de seriële poort.
@step
...
@step
En dat betekent: je werkbank wordt een geautomatiseerd testlab.

@reader
De agent gebruikt hiervoor `esptool` en een seriële monitor...
Zie ook [ESP-IDF documentatie](https://docs.espressif.com/).

@notes
Hier even demonstreren met de echte opstelling.

@en src=7c1e2a
## The AI agent can:
- Flash firmware
- Watch the serial log
- ...
=> Workbench is an automated test lab

@script
...


@slide cycle layout=diagram keypoints=cycle title=top-right

@diagram boxes
grid 4x4
box repo   "Stap 1 - Repo"      at 0,0   step=1
box idea   "Stap 2 - Idee"      at 1,0   step=2
box fsd    "Stap 3 - FSD"       at 2,1   step=3
...
arrow repo -> idea  step=2
arrow idea -> fsd   step=3
...

@nl
## Ishikawa-cirkel
@script
...

@en src=19bd04
## Ishikawa Circle
@labels repo="Step 1 - Repo" idea="Step 2 - Idea" fsd="Step 3 - FSD"
@script
...


@slide board layout=callouts

@image assets/esp32-board.jpg
@callout circle at 62%,40% r=6%  label="USB-poort" label.en="USB port"  step=1
@callout arrow  from 20%,80% to 35%,55% label="Reset-knop" label.en="Reset button" step=2

@nl
## Het bord
@script
...


@include @shared/slides/outro.md


@quiz h01
@question mc keypoint=agent-loop
@nl Welke taak kan de agent NIET zelf uitvoeren?
- [ ] Firmware flashen
- [ ] Seriële log lezen
- [x] Het bord fysiek vervangen
@en src=a01f33 Which task can the agent NOT perform on its own?
- [ ] Flash firmware
- [ ] Read the serial log
- [x] Physically replace the board
```

De actuele, volledige referentie staat in [docs/FORMAAT.md](docs/FORMAAT.md) (o.a. `@col`, `steps=`, code-regelstappen, `@@`).

Aandachtspunten in dit voorstel:
- Diagram-structuur (posities, stappen) staat **eenmaal**; alleen labels zijn per taal.
- Callout-posities in procenten → onafhankelijk van beeldresolutie.
- Slide-id's (`agent-can`, `cycle`) zijn stabiel → audio-cache, vertaal-hashes, klik-tijdstempels en includes blijven werken bij herordenen.

- (wordt aangevuld)
