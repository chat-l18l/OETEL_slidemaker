"""Deck model: the intermediate representation between source files and renderers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SOURCE_LANG = "nl"


@dataclass
class Loc:
    """Source location, for error messages."""

    file: Path
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line}"


@dataclass
class LangBlock:
    """Language-specific content of a slide."""

    lang: str
    body: str = ""
    script: list[str] = field(default_factory=list)  # segment n is spoken at step n
    reader: str = ""
    notes: str = ""
    labels: dict[str, str] = field(default_factory=dict)  # diagram/callout label overrides
    src: str | None = None  # hash of the NL source this translation is based on
    raw: str = ""  # raw source text, used for hashing
    loc: Loc | None = None


@dataclass
class ImageVisual:
    path: Path
    loc: Loc | None = None


@dataclass
class Callout:
    kind: str  # circle | arrow | box
    id: str
    label: dict[str, str]  # lang -> text
    step: int | None
    at: tuple[float, float] | None = None  # percent
    to: tuple[float, float] | None = None  # percent (arrow end)
    r: float = 5.0  # percent of image width (circle)
    size: tuple[float, float] | None = None  # percent (box)
    loc: Loc | None = None


@dataclass
class DiagramVisual:
    kind: str  # boxes | mermaid | graphviz | d2
    source: str
    loc: Loc | None = None


@dataclass
class Slide:
    id: str
    layout: str
    options: dict[str, str]
    keypoints: list[str]
    langs: dict[str, LangBlock] = field(default_factory=dict)
    image: ImageVisual | None = None
    callouts: list[Callout] = field(default_factory=list)
    diagram: DiagramVisual | None = None
    shared_raw: str = ""  # raw language-independent part (for hashing)
    loc: Loc | None = None

    def block(self, lang: str) -> LangBlock:
        """Content for `lang`, falling back to the source language."""
        return self.langs.get(lang) or self.langs.get(SOURCE_LANG) or LangBlock(lang=lang)


@dataclass
class QuizOption:
    text: str
    correct: bool


@dataclass
class QuizText:
    text: str = ""
    options: list[QuizOption] = field(default_factory=list)
    src: str | None = None
    loc: Loc | None = None


@dataclass
class Question:
    kind: str  # mc | open | truefalse
    keypoint: str | None
    langs: dict[str, QuizText] = field(default_factory=dict)
    loc: Loc | None = None


@dataclass
class Quiz:
    id: str
    questions: list[Question] = field(default_factory=list)
    loc: Loc | None = None


@dataclass
class Chapter:
    id: str
    path: Path
    title: dict[str, str]
    keypoints: dict[str, dict[str, str]]
    slides: list[Slide] = field(default_factory=list)
    quizzes: list[Quiz] = field(default_factory=list)


@dataclass
class Lesson:
    id: str
    path: Path
    title: dict[str, str]
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class Course:
    root: Path
    title: dict[str, str]
    langs: list[str]
    config: dict
    lessons: list[Lesson] = field(default_factory=list)

    @property
    def shared(self) -> Path:
        return self.root / "shared"
