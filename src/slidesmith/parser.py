"""Parser for chapter source files (Markdown with `@` directives).

The format is line based: a line starting with `@<known directive>` starts a new
structural element; everything else is content for the current element. Lines
inside fenced code blocks are never interpreted as directives.
"""

from __future__ import annotations

import hashlib
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .model import (
    Callout,
    Chapter,
    DiagramVisual,
    ImageVisual,
    LangBlock,
    Loc,
    Question,
    Quiz,
    QuizOption,
    QuizText,
    Slide,
    SOURCE_LANG,
)

LANGS = ("nl", "en")
LAYOUTS = (
    "title", "bullets", "image", "two-col", "code", "diagram",
    "quote", "table", "formula", "callouts",
)
DIRECTIVES = {
    "slide", "include", "quiz", "question", "image", "callout", "diagram",
    "script", "step", "reader", "notes", "labels", "col", *LANGS,
}
DIAGRAM_KINDS = ("boxes", "mermaid", "graphviz", "d2")
_CLOSERS = {"slide", "include", "quiz", "question", *LANGS}

_DIRECTIVE_RE = re.compile(r"^@([a-z][a-z0-9-]*)(?=\s|$)(.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_KV_RE = re.compile(r'\s*([A-Za-z_][\w.-]*)=("(?:[^"\\]|\\.)*"|\S+)')
_OPTION_RE = re.compile(r"^\s*[-*]\s+\[( |x|X)\]\s+(.*)$")


class SourceError(Exception):
    def __init__(self, msg: str, loc: Loc | None = None):
        super().__init__(f"{loc}: {msg}" if loc else msg)
        self.msg = msg
        self.loc = loc


@dataclass
class Diagnostics:
    warnings: list[tuple[Loc | None, str]] = field(default_factory=list)

    def warn(self, loc: Loc | None, msg: str) -> None:
        self.warnings.append((loc, msg))


def split_args(rest: str, loc: Loc) -> tuple[list[str], dict[str, str]]:
    """Split directive arguments into positionals and key=value options."""
    try:
        tokens = shlex.split(rest)
    except ValueError as e:
        raise SourceError(f"ongeldige argumenten: {e}", loc) from None
    pos: list[str] = []
    kw: dict[str, str] = {}
    for t in tokens:
        k, sep, v = t.partition("=")
        if sep and re.fullmatch(r"[A-Za-z_][\w.-]*", k):
            kw[k] = v
        else:
            pos.append(t)
    return pos, kw


def split_leading_kv(rest: str) -> tuple[dict[str, str], str]:
    """Parse leading key=value pairs; return them and the remaining free text."""
    kw: dict[str, str] = {}
    pos = 0
    while m := _KV_RE.match(rest, pos):
        v = m.group(2)
        if v.startswith('"'):
            v = v[1:-1].replace('\\"', '"')
        kw[m.group(1)] = v
        pos = m.end()
    return kw, rest[pos:].strip()


def parse_percent_pair(s: str, loc: Loc) -> tuple[float, float]:
    try:
        a, b = s.split(",")
        return float(a.strip().rstrip("%")), float(b.strip().rstrip("%"))
    except ValueError:
        raise SourceError(f"verwacht 'x%,y%', kreeg {s!r}", loc) from None


def parse_percent(s: str, loc: Loc) -> float:
    try:
        return float(s.rstrip("%"))
    except ValueError:
        raise SourceError(f"verwacht percentage, kreeg {s!r}", loc) from None


def src_hash(slide: Slide) -> str:
    """Hash of the source-language content a translation is based on."""
    nl = slide.langs.get(SOURCE_LANG)
    text = slide.shared_raw + "\n\x00\n" + (nl.raw if nl else "")
    norm = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return hashlib.sha256(norm.encode()).hexdigest()[:8]


def question_hash(q: Question) -> str:
    nl = q.langs.get(SOURCE_LANG)
    if not nl:
        return ""
    text = nl.text + "\n" + "\n".join(f"{o.correct}:{o.text}" for o in nl.options)
    return hashlib.sha256(text.strip().encode()).hexdigest()[:8]


def resolve_path(ref: str, base: Path, shared: Path | None, loc: Loc) -> Path:
    if ref.startswith("@shared/"):
        if shared is None:
            raise SourceError("@shared/ gebruikt buiten een cursus", loc)
        return (shared / ref[len("@shared/"):]).resolve()
    return (base / ref).resolve()


def _split_front_matter(lines: list[str], path: Path) -> tuple[dict, int]:
    if not lines or lines[0].strip() != "---":
        return {}, 0
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError as e:
                raise SourceError(f"ongeldige front matter: {e}", Loc(path, 1)) from None
            if not isinstance(data, dict):
                raise SourceError("front matter moet een mapping zijn", Loc(path, 1))
            return data, i + 1
    raise SourceError("front matter niet afgesloten met '---'", Loc(path, 1))


def lang_dict(value, default_lang: str = SOURCE_LANG) -> dict[str, str]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    return {default_lang: str(value)}


class _ChapterParser:
    def __init__(self, path: Path, shared: Path | None, diag: Diagnostics, stack: tuple[Path, ...]):
        self.path = path
        self.shared = shared
        self.diag = diag
        self.stack = stack + (path,)
        self.slides: list[Slide] = []
        self.quizzes: list[Quiz] = []
        # state
        self.slide: Slide | None = None
        self.block: LangBlock | None = None
        self.field: str | None = None  # body | script | reader | notes | diagram | shared
        self.quiz: Quiz | None = None
        self.question: Question | None = None
        self.qtext: QuizText | None = None
        self.in_fence = False

    def loc(self, i: int) -> Loc:
        return Loc(self.path, i + 1)

    # -- content accumulation -------------------------------------------------

    def _append(self, line: str, i: int) -> None:
        if self.qtext is not None:
            m = _OPTION_RE.match(line)
            if m:
                self.qtext.options.append(QuizOption(m.group(2).strip(), m.group(1) != " "))
            elif line.strip():
                self.qtext.text = (self.qtext.text + "\n" + line.strip()).strip()
            return
        if self.slide is None:
            if line.strip():
                raise SourceError("tekst buiten een @slide", self.loc(i))
            return
        if self.field == "diagram":
            assert self.slide.diagram is not None
            self.slide.diagram.source += line + "\n"
            self.slide.shared_raw += line + "\n"
        elif self.block is None:
            if line.strip():
                raise SourceError(
                    "tekst vóór @nl/@en; begin de inhoud met @nl", self.loc(i))
        else:
            self.block.raw += line + "\n"
            if self.field == "body":
                self.block.body += line + "\n"
            elif self.field == "script":
                self.block.script[-1] += line + "\n"
            elif self.field == "reader":
                self.block.reader += line + "\n"
            elif self.field == "notes":
                self.block.notes += line + "\n"

    # -- directives -------------------------------------------------------------

    def _finish_slide(self) -> None:
        if self.slide is None:
            return
        s = self.slide
        for b in s.langs.values():
            b.body = b.body.strip("\n")
            b.reader = b.reader.strip()
            b.notes = b.notes.strip()
            b.script = [seg.strip() for seg in b.script]
        if SOURCE_LANG not in s.langs:
            self.diag.warn(s.loc, f"slide '{s.id}' heeft geen @{SOURCE_LANG}-blok")
        self.slides.append(s)
        self.slide = None
        self.block = None
        self.field = None

    def _finish_quiz(self) -> None:
        self.qtext = None
        self.question = None
        self.quiz = None

    def _close(self, name: str, line: int) -> None:
        """Record where the open language block / quiz text ends, for in-place rewrites."""
        if name in _CLOSERS:
            if self.block is not None and self.block.end is None:
                self.block.end = line
            if self.qtext is not None and self.qtext.end is None:
                self.qtext.end = line

    def directive(self, name: str, rest: str, i: int) -> None:
        loc = self.loc(i)
        self._close(name, i + 1)
        if name == "slide":
            self._finish_slide()
            self._finish_quiz()
            pos, kw = split_args(rest, loc)
            if not pos:
                raise SourceError("@slide verwacht een id", loc)
            layout = kw.pop("layout", "bullets")
            if layout not in LAYOUTS:
                raise SourceError(
                    f"onbekende layout '{layout}' (kies uit: {', '.join(LAYOUTS)})", loc)
            kps = [k for k in kw.pop("keypoints", "").split(",") if k]
            self.slide = Slide(id=pos[0], layout=layout, options=kw, keypoints=kps, loc=loc)
            self.field = "shared"
            return
        if name == "include":
            self._finish_slide()
            self._finish_quiz()
            pos, _ = split_args(rest, loc)
            if len(pos) != 1:
                raise SourceError("@include verwacht één pad", loc)
            target = resolve_path(pos[0], self.path.parent, self.shared, loc)
            if target in self.stack:
                raise SourceError(f"recursieve include van {target}", loc)
            if not target.exists():
                raise SourceError(f"include niet gevonden: {target}", loc)
            sub = parse_file(target, self.shared, self.diag, self.stack)
            self.slides.extend(sub.slides)
            self.quizzes.extend(sub.quizzes)
            return
        if name == "quiz":
            self._finish_slide()
            self._finish_quiz()
            pos, _ = split_args(rest, loc)
            self.quiz = Quiz(id=pos[0] if pos else f"quiz{len(self.quizzes) + 1}", loc=loc)
            self.quizzes.append(self.quiz)
            return
        if name == "question":
            if self.quiz is None:
                raise SourceError("@question buiten een @quiz", loc)
            pos, kw = split_args(rest, loc)
            kind = pos[0] if pos else "mc"
            if kind not in ("mc", "open", "truefalse"):
                raise SourceError(f"onbekend vraagtype '{kind}' (mc, open, truefalse)", loc)
            self.question = Question(kind=kind, keypoint=kw.get("keypoint"), loc=loc)
            self.quiz.questions.append(self.question)
            self.qtext = None
            return

        if name in LANGS and self.question is not None:
            kw, text = split_leading_kv(rest)
            self.qtext = QuizText(text=text, src=kw.get("src"), loc=loc)
            self.question.langs[name] = self.qtext
            return

        if self.slide is None:
            raise SourceError(f"@{name} buiten een @slide", loc)
        s = self.slide

        if name in LANGS:
            if name in s.langs:
                raise SourceError(f"dubbel @{name}-blok in slide '{s.id}'", loc)
            kw, text = split_leading_kv(rest)
            self.block = LangBlock(lang=name, src=kw.get("src"), loc=loc)
            s.langs[name] = self.block
            self.field = "body"
            if text:
                self.block.body += text + "\n"
                self.block.raw += text + "\n"
            return

        if name in ("image", "callout", "diagram"):
            if self.block is not None:
                raise SourceError(
                    f"@{name} hoort vóór de taalblokken (@nl/@en) van de slide", loc)
            s.shared_raw += f"@{name}{rest}\n"
            if name == "image":
                pos, _ = split_args(rest, loc)
                if len(pos) != 1:
                    raise SourceError("@image verwacht één pad", loc)
                s.image = ImageVisual(resolve_path(pos[0], self.path.parent, self.shared, loc), loc)
            elif name == "callout":
                s.callouts.append(self._callout(rest, loc, len(s.callouts) + 1))
            else:
                pos, _ = split_args(rest, loc)
                kind = pos[0] if pos else "boxes"
                if kind not in DIAGRAM_KINDS:
                    raise SourceError(
                        f"onbekend diagramtype '{kind}' (kies uit: {', '.join(DIAGRAM_KINDS)})", loc)
                if s.diagram is not None:
                    raise SourceError("maximaal één @diagram per slide", loc)
                s.diagram = DiagramVisual(kind=kind, source="", loc=loc)
                self.field = "diagram"
                return
            self.field = "shared"
            return

        if self.block is None:
            raise SourceError(f"@{name} hoort binnen een taalblok (@nl/@en)", loc)
        b = self.block
        b.raw += f"@{name}{rest}\n"
        if name == "script":
            if b.script:
                raise SourceError("dubbel @script-blok", loc)
            b.script.append("")
            self.field = "script"
        elif name == "step":
            if self.field != "script":
                raise SourceError("@step mag alleen binnen @script", loc)
            b.script.append("")
        elif name in ("reader", "notes"):
            self.field = name
        elif name == "labels":
            kw, extra = split_leading_kv(rest)
            if extra:
                raise SourceError(f"@labels verwacht alleen key=\"waarde\", niet {extra!r}", loc)
            b.labels.update(kw)
        elif name == "col":
            if self.field != "body":
                raise SourceError("@col mag alleen in de slide-inhoud", loc)
            b.body += "@col\n"

    def _callout(self, rest: str, loc: Loc, n: int) -> Callout:
        pos, kw = split_args(rest, loc)
        if not pos or pos[0] not in ("circle", "arrow", "box"):
            raise SourceError("@callout verwacht type circle, arrow of box", loc)
        c = Callout(
            kind=pos[0],
            id=kw.get("id", f"c{n}"),
            label={k.partition(".")[2] or SOURCE_LANG: v
                   for k, v in kw.items() if k == "label" or k.startswith("label.")},
            step=int(kw["step"]) if "step" in kw else None,
            loc=loc,
        )
        it = iter(pos[1:])
        for word in it:
            val = next(it, None)
            if val is None:
                raise SourceError(f"'{word}' verwacht een waarde", loc)
            if word in ("at", "from"):
                c.at = parse_percent_pair(val, loc)
            elif word == "to":
                c.to = parse_percent_pair(val, loc)
            else:
                raise SourceError(f"onbekend woord '{word}' in @callout", loc)
        if "r" in kw:
            c.r = parse_percent(kw["r"], loc)
        if "size" in kw:
            c.size = parse_percent_pair(kw["size"], loc)
        if c.at is None:
            raise SourceError("@callout mist 'at x%,y%' (of 'from' voor een pijl)", loc)
        if c.kind == "arrow" and c.to is None:
            raise SourceError("@callout arrow mist 'to x%,y%'", loc)
        if c.kind == "box" and c.size is None:
            raise SourceError("@callout box mist size=b%,h%", loc)
        return c

    # -- main loop --------------------------------------------------------------

    def run(self, lines: list[str], start: int) -> None:
        for i in range(start, len(lines)):
            line = lines[i]
            if _FENCE_RE.match(line) and self.field in ("body", "reader", "notes", "script"):
                self.in_fence = not self.in_fence
                self._append(line, i)
                continue
            if not self.in_fence:
                m = _DIRECTIVE_RE.match(line)
                if m and m.group(1) in DIRECTIVES:
                    self.directive(m.group(1), m.group(2), i)
                    continue
                if m and not line.startswith("@@"):
                    raise SourceError(
                        f"onbekende directive '@{m.group(1)}' "
                        "(gebruik '@@' aan het begin van de regel voor een letterlijke '@')",
                        self.loc(i))
                if line.startswith("@@"):
                    line = line[1:]
            self._append(line, i)
        if self.in_fence:
            self.diag.warn(Loc(self.path, len(lines)), "codeblok niet afgesloten")
        self._close("slide", len(lines) + 1)
        self._finish_slide()


@dataclass
class ParsedFile:
    front: dict
    slides: list[Slide]
    quizzes: list[Quiz]


def parse_text(text: str, path: Path, shared: Path | None = None,
               diag: Diagnostics | None = None,
               stack: tuple[Path, ...] = ()) -> ParsedFile:
    diag = diag if diag is not None else Diagnostics()
    lines = text.splitlines()
    front, start = _split_front_matter(lines, path)
    p = _ChapterParser(path, shared, diag, stack)
    p.run(lines, start)
    return ParsedFile(front, p.slides, p.quizzes)


def parse_file(path: Path, shared: Path | None = None, diag: Diagnostics | None = None,
               stack: tuple[Path, ...] = ()) -> ParsedFile:
    return parse_text(path.read_text(encoding="utf-8"), path.resolve(), shared, diag, stack)


def parse_chapter(path: Path, shared: Path | None = None,
                  diag: Diagnostics | None = None) -> Chapter:
    diag = diag if diag is not None else Diagnostics()
    pf = parse_file(path, shared, diag)
    front = pf.front
    keypoints = {str(k): lang_dict(v) for k, v in (front.get("keypoints") or {}).items()}
    chapter = Chapter(
        id=str(front.get("id") or path.stem),
        path=path.resolve(),
        title=lang_dict(front.get("title")) or {SOURCE_LANG: path.stem},
        keypoints=keypoints,
        slides=pf.slides,
        quizzes=pf.quizzes,
    )
    seen: dict[str, Slide] = {}
    for s in chapter.slides:
        if s.id in seen:
            raise SourceError(f"slide-id '{s.id}' komt al voor op {seen[s.id].loc}", s.loc)
        seen[s.id] = s
        for kp in s.keypoints:
            if kp not in keypoints:
                diag.warn(s.loc, f"onbekend keypoint '{kp}' in slide '{s.id}'")
    for q in chapter.quizzes:
        for question in q.questions:
            if question.keypoint and question.keypoint not in keypoints:
                diag.warn(question.loc, f"onbekend keypoint '{question.keypoint}' in quizvraag")
    return chapter
