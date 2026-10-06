# Bronformaat — referentie

Een hoofdstuk is één `.md`-bestand: Markdown voor inhoud, regels die met `@` beginnen voor structuur.
Directieven worden **niet** herkend binnen codeblokken. Een regel die letterlijk met `@` moet
beginnen schrijf je als `@@`.

## Projectstructuur

```
cursus/
  course.yaml            # titel, talen, accentkleur, logo, tijdbalk, spreeksnelheid
  shared/                # herbruikbaar: @shared/slides/x.md, @shared/assets/logo.svg
  lessen/
    01-naam/
      lesson.yaml        # id, titel, volgorde van hoofdstukken (optioneel)
      01-hoofdstuk.md
      assets/
  build/                 # gegenereerd (niet in versiebeheer)
```

`course.yaml`:

```yaml
title: {nl: Cursustitel, en: Course title}
langs: [nl, en]
accent: "#F0A030"
logo: shared/assets/logo.svg     # optioneel
logo_position: bottom-right      # bottom-right | bottom-left | top-right | top-left
timebar: true
wpm: {nl: 140, en: 150}          # spreeksnelheid voor tijdschatting
lessons: [lessen/01-naam]        # optioneel; standaard alle mappen in lessen/
author: Naam                     # optioneel; op de titelpagina van PDF's
tts:                             # conceptvideo (slides video)
  provider: elevenlabs
  model: eleven_multilingual_v2
  voice: {nl: <voice-id>, en: <voice-id>}
  settings: {stability: 0.5, similarity_boost: 0.75, speed: 1.0}
video:
  fps: 30
  lead: 0.3                      # stilte vóór elk scriptfragment (s)
  tail: 0.6                      # stilte na elk scriptfragment (s)
  preset: veryfast               # x264-preset; medium = kleiner bestand, trager
  crf: 20
pdf:                             # optioneel; alles staat standaard aan
  title_page: true
  toc: true
  page_numbers: true
  sources: true                  # bronnenlijst uit links in reader- en slidetekst
  quiz: true                     # vragen per hoofdstuk + antwoorden in bijlage (reader)
```

`lesson.yaml`:

```yaml
id: les01
title: {nl: Les 1, en: Lesson 1}
chapters: [01-intro.md, 02-werkwijze.md]   # optioneel; standaard *.md op naam
```

## Hoofdstukbestand

```markdown
---
id: intro
title: {nl: Introductie, en: Introduction}
keypoints:
  agent-loop:
    nl: Een AI-agent kan de test-loop zelfstandig doorlopen.
    en: An AI agent can run the test loop on its own.
---

@slide <id> layout=<layout> [keypoints=a,b] [steps=auto|none] [title=top-right|top-left] [logo=off] [class=x,y]

(taalonafhankelijke visuals: @image, @callout, @diagram)

@nl
(slide-inhoud in Markdown)

@script
(gesproken tekst bij het verschijnen van de slide)
@step
(gesproken tekst bij onthulstap 1)
@step
(… stap 2, enz.)

@reader
(uitgebreide tekst voor de reader-PDF)

@notes
(notities voor de presentator)

@en src=<hash>
(zelfde opbouw, Engels)
```

- **Slide-id's** zijn uniek per hoofdstuk en stabiel: ze worden gebruikt in URL's, audio-cache en vertaal-hashes. Hernoem ze niet zonder reden.
- **Volgorde:** visuals → `@nl` → `@en`. Binnen een taalblok: inhoud, daarna `@script`, `@reader`, `@notes`, `@labels` in willekeurige volgorde.
- Ontbreekt een taal, dan wordt NL gebruikt (met waarschuwing).

## Layouts

| layout | inhoud |
|---|---|
| `title` | `# Titel` + ondertitel-alinea |
| `bullets` | `## Titel`, lijst, optioneel `=> takeaway`. Lijstitems en takeaway zijn automatisch onthulstappen |
| `image` | `@image pad` + optioneel `## Titel` en onderschrift |
| `two-col` | inhoud met `@col` als kolomscheiding |
| `code` | `## Titel` + codeblok, optioneel met regelstappen |
| `diagram` | `@diagram <type>` + `## Titel` (`title=top-right` voor titel rechtsboven) |
| `quote` | `> citaat` |
| `table` | Markdown-tabel |
| `formula` | `$$ … $$` (KaTeX); inline `$ … $` werkt in alle layouts |
| `callouts` | `@image` + `@callout`-regels |

## Onthulstappen (progressive disclosure)

- `steps=auto` (standaard bij `bullets`): elk lijstitem op het hoogste niveau en elke `=>`-regel is een stap.
- Diagrammen en callouts: `step=N` per element.
- Code: ` ```python steps=1-2|4-6|8 ` licht per stap de genoemde regels op.
- Het script heeft per stap één fragment: `@script` = stap 0, elke `@step` de volgende.
  `slides check` waarschuwt als het aantal fragmenten niet klopt met het aantal stappen.

## Takeaway

```markdown
=> Workbench is een geautomatiseerd testlab
```

Een regel die begint met `=> ` wordt een uitgelichte conclusieregel met pijl.

## Plaatjes

- `@image assets/foto.jpg` (slide-visual) of `![](assets/foto.png)` in de inhoud.
- Paden zijn relatief aan het hoofdstukbestand, of `@shared/...`.

## Callouts

```markdown
@image assets/bord.png
@callout circle at 15%,50% r=6% label="USB-poort" label.en="USB port" step=1
@callout arrow from 22%,88% to 30%,68% label="Reset-knop" step=2
@callout box at 43%,29% size=26%,28% label="ESP32" step=3
```

Posities zijn percentages van het plaatje (dus onafhankelijk van de resolutie).
Engelse labels via `label.en=` of `@labels <id>="…"` in het `@en`-blok (id's zijn `c1`, `c2`, … of `id=`).

## Diagrammen

### boxes (eigen notatie, posities als tekst)

```markdown
@diagram boxes
grid 4x4                                   # kolommen x rijen
box repo "Stap 1 - Repo" at 0,0 step=1     # kolom,rij (fracties mogen)
box idee "Stap 2 - Idee" at 1.5,0 span=2,1 style=outline   # style: fill | outline | plain
arrow repo -> idee step=2 label="push"     # ook <-> en style=dashed
```

Breedte van een blok volgt de tekst; alle blokken krijgen dezelfde lettergrootte.
Regelafbreking in een label: `\n`. Engelse labels: `@labels repo="Step 1 - Repo" idee="…"` in `@en`.

### mermaid, graphviz, d2

```markdown
@diagram mermaid
flowchart LR
  A --> B
```

Vereist respectievelijk `mmdc`, `dot` of `d2` op het pad. Resultaat wordt gecachet.

## Quiz

```markdown
@quiz <id>
@question mc keypoint=agent-loop       # mc | open | truefalse
@nl Welke taak kan de agent NIET zelf?
- [ ] Firmware flashen
- [x] Het bord vervangen
@en src=<hash> Which task can the agent NOT do?
- [ ] Flash firmware
- [x] Replace the board
```

## Includes

`@include @shared/slides/outro.md` voegt alle slides uit dat bestand op die plek in.

## PDF

`slides pdf` maakt per les en taal:

- `<les>-slides.pdf`: 16:9, één slide per pagina in de eindstand (alle stappen zichtbaar), met titelpagina en inhoudsopgave.
- `<les>-reader.pdf`: A4, per slide de slide met daaronder de `@reader`-tekst. Per hoofdstuk staan de kernpunten bovenaan en de quizvragen onderaan. Achterin: antwoorden en bronnen.

Beide gebruiken het printthema: wit papier, donkere tekst, diagrammen opnieuw gerenderd in lichte kleuren.
De versie uit git/hg/svn komt op de titelpagina. Tekst met te weinig contrast geeft een waarschuwing.
Een slide zonder kop krijgt in de inhoudsopgave de eerste tekstregel als titel.

## Video

`slides video [pad] [--lang nl] [--yes] [--silent] [--subs nl,en]` maakt per les en taal in `build/video/<taal>/`:

- `<les>.mp4`: 1920×1080, één beeld per onthulstap. Het `@script`-fragment van die stap wordt ingesproken via TTS, en de tijdbalk per hoofdstuk loopt vloeiend mee.
- `<les>.<taal>.srt` en `.vtt`: ondertitels. In de gesproken taal zijn ze exact getimed op de audio (per teken). Andere talen worden over dezelfde spreekmomenten verdeeld.
- `<les>-chapters.txt`: YouTube-hoofdstukken (`00:00 Titel`), om in de videobeschrijving te plakken.

Elke stap duurt `lead` + audio + `tail`. Een stap zonder script krijgt de geschatte duur.
Audio wordt gecachet per fragment, dus na een wijziging wordt alleen het gewijzigde fragment opnieuw ingesproken.
Vóór betaalde synthese toont de tool het aantal tekens en vraagt om bevestiging (`--yes` slaat dat over).
`--silent` maakt een video zonder audio, met geschatte timing.

De API-key staat in `ELEVENLABS_API_KEY`, of in `~/.config/slidesmith/secrets.env` (buiten de repo):

```
ELEVENLABS_API_KEY=sk_...
```

### Uitspraak: lexicon.yaml

In de cursusroot. Het past alleen de gesproken tekst aan; de ondertitels tonen de geschreven tekst.

```yaml
nl:
  ESP32: E S P tweeëndertig
  USB: U S B
en:
  ESP32: E S P thirty-two
```

Termen worden als heel woord vervangen, hoofdlettergevoelig.

## Vertalingen

- `@en src=<hash>`: de hash van de NL-inhoud (plus visuals) waarop de vertaling gebaseerd is.
- `slides check` meldt ontbrekende en verouderde vertalingen.
- `slides stamp [pad] [--id slide]` zet de hash op de huidige NL-versie (na review van de vertaling).
