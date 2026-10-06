---
id: intro
title:
  nl: Introductie
  en: Introduction
keypoints:
  agent-loop:
    nl: Een AI-agent kan de volledige test-loop zelfstandig doorlopen.
    en: An AI agent can run the full test loop on its own.
---

@slide titel layout=title

@nl
# De werkbank als testlab
AI-agents die zelf flashen, meten en testen

@script
Welkom! Vandaag kijken we hoe je je elektronica-werkbank verandert in een geautomatiseerd testlab.

@reader
In deze les bouwen we stap voor stap een opstelling waarin een AI-agent
zelfstandig firmware kan flashen en testen.

@en src=80ba591b
# The workbench as a test lab
AI agents that flash, measure and test on their own

@script
Welcome! Today we look at how to turn your electronics workbench into an automated test lab.

@reader
In this lesson we build, step by step, a setup in which an AI agent can
flash and test firmware on its own.


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
Om te beginnen flasht hij zelf de firmware naar het bord.
@step
Daarna leest hij mee op de seriële poort, net zoals jij dat zou doen.
@step
Hij draait de tests die we hebben voorbereid.
@step
En hij controleert of de resultaten kloppen met wat we verwachten.
@step
Gaat er iets mis, dan past hij de code aan en begint opnieuw.
@step
Kortom: je werkbank wordt een geautomatiseerd testlab.

@reader
De agent gebruikt hiervoor gewone command-line tools zoals `esptool` en een
seriële monitor. Zie ook de [ESP-IDF documentatie](https://docs.espressif.com/).

@notes
Hier even de echte opstelling laten zien.

@en src=e204ef0c
## The AI agent can:
- Flash firmware
- Watch the serial log
- Run tests
- Validate the results
- Fix problems in the code if needed

=> Workbench is an automated test lab

@script
So what can such an agent actually do?
@step
First of all, it flashes the firmware to the board by itself.
@step
Then it watches the serial port, just like you would.
@step
It runs the tests we prepared.
@step
And it checks whether the results match what we expect.
@step
If something goes wrong, it fixes the code and starts over.
@step
In short: your workbench becomes an automated test lab.

@reader
The agent uses ordinary command-line tools such as `esptool` and a serial
monitor. See also the [ESP-IDF documentation](https://docs.espressif.com/).

@notes
Show the real setup here.


@slide kernidee layout=quote

@nl
> Laat de machine het saaie werk doen, en houd zelf het overzicht.

@script
Het idee is simpel: laat de machine het saaie werk doen, en houd zelf het overzicht.

@en src=ef7d2df0
> Let the machine do the boring work, and keep the overview yourself.

@script
The idea is simple: let the machine do the boring work, and keep the overview yourself.


@quiz intro
@question mc keypoint=agent-loop
@nl Welke taak kan de agent NIET zelf uitvoeren?
- [ ] Firmware flashen
- [ ] De seriële log lezen
- [x] Het bord fysiek vervangen
@en src=b8d9dbf4 Which task can the agent NOT perform on its own?
- [ ] Flash firmware
- [ ] Read the serial log
- [x] Physically replace the board
