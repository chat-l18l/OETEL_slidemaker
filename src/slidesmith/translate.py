"""`slides translate`: fill in missing or outdated translations with Claude.

Work units are slides, chapter headers (title + keypoints) and quiz questions. A slide
is up to date when its `@en src=` equals the hash of the current NL content. Every
answer is checked against the NL structure (list items, takeaways, columns, code block
line counts, script fragments, labels) before it is written; a unit that fails is
retried once with the errors, then skipped with a warning.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import ai, boxes
from .model import Chapter, Course, Loc, Question, Slide, SOURCE_LANG
from .parser import Diagnostics, SourceError, question_hash, src_hash

SLIDE_SCHEMA = {
    "type": "object",
    "properties": {
        "body": {"type": "string"},
        "script": {"type": "array", "items": {"type": "string"}},
        "reader": {"type": "string"},
        "notes": {"type": "string"},
        "labels": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["id", "text"], "additionalProperties": False}},
    },
    "required": ["body", "script", "reader", "notes", "labels"],
    "additionalProperties": False,
}

HEADER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "keypoints": {"type": "array", "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["id", "text"], "additionalProperties": False}},
    },
    "required": ["title", "keypoints"],
    "additionalProperties": False,
}

QUIZ_SCHEMA = {
    "type": "object",
    "properties": {"questions": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "text": {"type": "string"},
                       "options": {"type": "array", "items": {"type": "string"}}},
        "required": ["id", "text", "options"], "additionalProperties": False}}},
    "required": ["questions"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- glossary

def load_glossary(course: Course) -> dict:
    """glossary.yaml: {keep: [terms], terms: {nl: en}}."""
    path = course.root / "glossary.yaml"
    if not path.exists():
        return {"keep": [], "terms": {}}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"keep": [str(t) for t in data.get("keep") or []],
            "terms": {str(k): str(v) for k, v in (data.get("terms") or {}).items()}}


def glossary_text(g: dict) -> str:
    if not g["keep"] and not g["terms"]:
        return ""
    lines = ["## Glossary", ""]
    if g["terms"]:
        lines += ["Translate these terms like this:", ""]
        lines += [f"- {nl} → {en}" for nl, en in sorted(g["terms"].items())]
        lines.append("")
    if g["keep"]:
        lines += ["Keep these terms unchanged:", "", ", ".join(sorted(g["keep"])), ""]
    return "\n".join(lines)


# ---------------------------------------------------------------- structure checks

_ITEM_RE = re.compile(r"^(?:[-*+]|\d+[.)])\s")
_FENCE_RE = re.compile(r"^\s*(```|~~~)(.*)$")


def signature(body: str) -> dict:
    """The parts of a slide body that determine its layout and reveal steps."""
    sig = {"items": 0, "takeaways": 0, "cols": 0, "headings": [], "code": [], "table_rows": 0, "math": 0}
    in_code, code_info, code_lines = False, "", 0
    for line in body.splitlines():
        m = _FENCE_RE.match(line)
        if m:
            if in_code:
                sig["code"].append((code_info, code_lines))
                in_code = False
            else:
                in_code, code_info, code_lines = True, m.group(2).strip(), 0
            continue
        if in_code:
            code_lines += 1
            continue
        if _ITEM_RE.match(line):
            sig["items"] += 1
        elif line.startswith("=> "):
            sig["takeaways"] += 1
        elif line.strip() == "@col":
            sig["cols"] += 1
        elif m := re.match(r"^(#{1,6})\s", line):
            sig["headings"].append(len(m.group(1)))
        elif line.lstrip().startswith("|"):
            sig["table_rows"] += 1
        sig["math"] += line.count("$$")
    return sig


def check_slide(nl: dict, en: dict, label_ids: set[str]) -> list[str]:
    errors = []
    a, b = signature(nl["body"]), signature(en["body"])
    names = {"items": "lijstitems", "takeaways": "=>-regels", "cols": "@col-regels",
             "headings": "koppen", "code": "codeblokken (info, regels)",
             "table_rows": "tabelregels", "math": "$$-blokken"}
    for k, name in names.items():
        if a[k] != b[k]:
            errors.append(f"{name}: NL {a[k]}, EN {b[k]}")
    if len(en["script"]) != len(nl["script"]):
        errors.append(f"script-fragmenten: NL {len(nl['script'])}, EN {len(en['script'])}")
    got = {x["id"] for x in en["labels"]}
    if got != label_ids:
        errors.append(f"labels: verwacht {sorted(label_ids)}, kreeg {sorted(got)}")
    for line in en["body"].splitlines():
        if line.startswith("@") and line.strip() != "@col" and not line.startswith("@@"):
            errors.append(f"regel begint met '@': {line[:40]!r}")
    return errors


# ---------------------------------------------------------------- units of work

@dataclass
class SlideUnit:
    chapter: Chapter
    slide: Slide
    labels_nl: dict[str, str]
    reason: str  # "ontbreekt" | "verouderd" | "geforceerd"
    result: dict | None = None
    errors: list[str] = field(default_factory=list)


def slide_labels(slide: Slide) -> dict[str, str]:
    """Translatable labels of diagram boxes/arrows and callouts without an inline English label."""
    labels: dict[str, str] = {}
    if slide.diagram and slide.diagram.kind == "boxes":
        d = boxes.parse(slide.diagram.source, slide.diagram.loc)
        labels.update({b.id: b.label for b in d.boxes.values()})
        labels.update({a.id: a.label for a in d.arrows if a.label})
    for c in slide.callouts:
        if "en" not in c.label and c.label.get(SOURCE_LANG):
            labels[c.id] = c.label[SOURCE_LANG]
    nl = slide.langs.get(SOURCE_LANG)
    if nl:
        labels.update(nl.labels)
    return labels


def block_dict(slide: Slide, lang: str) -> dict:
    b = slide.langs[lang]
    return {"body": b.body, "script": b.script, "reader": b.reader, "notes": b.notes}


def slide_request(u: SlideUnit, lang: str) -> str:
    s = u.slide
    req = {
        "unit": "slide",
        "target_language": lang,
        "chapter": u.chapter.title.get(SOURCE_LANG, ""),
        "slide_id": s.id,
        "layout": s.layout,
        "nl": block_dict(s, SOURCE_LANG),
        "labels_nl": [{"id": k, "text": v} for k, v in u.labels_nl.items()],
    }
    if lang in s.langs and u.reason != "ontbreekt":
        prev = block_dict(s, lang)
        prev["labels"] = [{"id": k, "text": v} for k, v in s.langs[lang].labels.items()]
        req["previous_en"] = prev
    return json.dumps(req, ensure_ascii=False, indent=1)


def render_block(lang: str, src: str, en: dict, labels_nl: dict[str, str]) -> list[str]:
    """Serialize a translated language block in the source format."""
    out = [f"@{lang} src={src}"]
    body = en["body"].strip("\n")
    if body:
        out.append(body)
    labels = {x["id"]: x["text"] for x in en["labels"] if x["id"] in labels_nl}
    if labels:
        out.append("")
        out.append("@labels " + " ".join(
            f'{k}="{v.replace(chr(34), chr(92) + chr(34))}"' for k, v in labels.items()))
    if any(seg.strip() for seg in en["script"]):
        out += ["", "@script", en["script"][0].strip()]
        for seg in en["script"][1:]:
            out += ["@step", seg.strip()]
    if en["reader"].strip():
        out += ["", "@reader", en["reader"].strip()]
    if en["notes"].strip():
        out += ["", "@notes", en["notes"].strip()]
    return out


# ---------------------------------------------------------------- file edits

class Edits:
    """Line-based edits per file, applied bottom-up so earlier line numbers stay valid."""

    def __init__(self) -> None:
        self.by_file: dict[Path, list[tuple[int, int, list[str]]]] = defaultdict(list)

    def replace(self, path: Path, start: int, end: int, lines: list[str]) -> None:
        """Replace 1-based lines [start, end) with `lines`."""
        self.by_file[path].append((start, end, lines))

    def apply(self) -> list[Path]:
        for path, edits in self.by_file.items():
            text = path.read_text(encoding="utf-8").split("\n")
            for start, end, lines in sorted(edits, key=lambda e: e[0], reverse=True):
                text[start - 1:end - 1] = lines
            path.write_text("\n".join(text), encoding="utf-8")
        return list(self.by_file)


def _region_end(path_lines: list[str], start: int, end: int) -> int:
    """Exclusive end of a block without its trailing blank lines (1-based)."""
    while end - 1 > start and not path_lines[end - 2].strip():
        end -= 1
    return end


# ---------------------------------------------------------------- chapter header (front matter)

def header_missing(ch: Chapter, lang: str) -> bool:
    return lang not in ch.title or any(lang not in t for t in ch.keypoints.values())


def header_edits(ch: Chapter, lang: str, result: dict, edits: Edits, diag: Diagnostics) -> None:
    """Insert `en:` lines into the YAML front matter (block style only)."""
    lines = ch.path.read_text(encoding="utf-8").split("\n")
    q = lambda s: json.dumps(s, ensure_ascii=False)  # noqa: E731 - valid YAML double-quoted

    def insert_after_nl(key_line: int, child_indent: str, value: str) -> bool:
        """Add `<lang>: value` after the `nl:` child of the mapping that starts at key_line."""
        key_indent = len(lines[key_line]) - len(lines[key_line].lstrip())
        for j in range(key_line + 1, len(lines)):
            line = lines[j]
            if line.strip() == "---" or (line.strip() and len(line) - len(line.lstrip()) <= key_indent):
                return False
            if line.startswith(f"{child_indent}{SOURCE_LANG}:"):
                edits.replace(ch.path, j + 2, j + 2, [f"{child_indent}{lang}: {q(value)}"])
                return True
        return False

    for j, line in enumerate(lines):
        if line.strip() == "---" and j > 0:
            break
        if lang not in ch.title and re.match(r"^title:\s*$", line):
            if not insert_after_nl(j, "  ", result["title"]):
                diag.warn(Loc(ch.path, j + 1), "kon titelvertaling niet invoegen")
        elif lang not in ch.title and (m := re.match(r"^title:\s*(\S.*)$", line)):
            if m.group(1).startswith("{"):
                diag.warn(Loc(ch.path, j + 1), f"titel in inline-notatie; voeg '{lang}: {result['title']}' zelf toe")
            else:
                edits.replace(ch.path, j + 1, j + 2, ["title:", f"  {SOURCE_LANG}: {q(ch.title[SOURCE_LANG])}",
                                                      f"  {lang}: {q(result['title'])}"])
        elif m := re.match(r"^  ([\w-]+):\s*$", line):
            kp = m.group(1)
            if kp in ch.keypoints and lang not in ch.keypoints[kp]:
                text = next((x["text"] for x in result["keypoints"] if x["id"] == kp), None)
                if text is None or not insert_after_nl(j, "    ", text):
                    diag.warn(Loc(ch.path, j + 1), f"kon keypoint '{kp}' niet vertalen/invoegen")


# ---------------------------------------------------------------- main

@dataclass
class Plan:
    slides: list[SlideUnit] = field(default_factory=list)
    headers: list[Chapter] = field(default_factory=list)
    quizzes: list[tuple[Chapter, list[Question]]] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.slides or self.headers or self.quizzes)

    def describe(self) -> list[str]:
        out = [f"slide {u.slide.id} ({u.reason})" for u in self.slides]
        out += [f"hoofdstukkop {ch.id}" for ch in self.headers]
        out += [f"quiz {ch.id}: {len(qs)} vraag/vragen" for ch, qs in self.quizzes]
        return out


def plan(course: Course, lang: str, ids: set[str] | None, force: bool) -> Plan:
    p = Plan()
    seen: set[tuple[Path, int]] = set()  # an included slide appears once
    for lesson in course.lessons:
        for ch in lesson.chapters:
            if header_missing(ch, lang) and not ids:
                p.headers.append(ch)
            for s in ch.slides:
                nl = s.langs.get(SOURCE_LANG)
                if nl is None or (ids and s.id not in ids) or (s.loc.file, s.loc.line) in seen:
                    continue
                seen.add((s.loc.file, s.loc.line))
                b = s.langs.get(lang)
                if b is None:
                    reason = "ontbreekt"
                elif b.src != src_hash(s):
                    reason = "verouderd"
                elif force:
                    reason = "geforceerd"
                else:
                    continue
                p.slides.append(SlideUnit(ch, s, slide_labels(s), reason))
            qs = []
            for quiz in ch.quizzes:
                if ids and quiz.id not in ids:
                    continue
                for q in quiz.questions:
                    if SOURCE_LANG in q.langs and (q.langs.get(lang) is None
                                                   or q.langs[lang].src != question_hash(q) or force):
                        qs.append(q)
            if qs:
                p.quizzes.append((ch, qs))
    return p


def _translate_slide(claude: ai.Claude, system: str, u: SlideUnit, lang: str) -> None:
    nl = block_dict(u.slide, SOURCE_LANG)
    user = slide_request(u, lang)
    for attempt in range(2):
        result = claude.json(system, user, SLIDE_SCHEMA)
        errors = check_slide(nl, result, set(u.labels_nl))
        if not errors:
            u.result, u.errors = result, []
            return
        u.errors = errors
        user = (slide_request(u, lang) + "\n\nYour previous answer broke the slide structure:\n- "
                + "\n- ".join(errors) + "\nFix these and answer again.")


def run(course: Course, lang: str, diag: Diagnostics, ids: set[str] | None = None,
        force: bool = False, confirm=lambda p: True) -> tuple[list[str], ai.Usage | None, str]:
    """Translate everything that needs it. Returns (changed descriptions, usage, model)."""
    if lang == SOURCE_LANG:
        raise SourceError(f"{SOURCE_LANG} is de brontaal; kies een doeltaal (bv. --lang en)")
    p = plan(course, lang, ids, force)
    if p.empty():
        return [], None, ""
    if not confirm(p):
        raise SourceError("gestopt")
    claude = ai.Claude(course)
    system = ai.prompt("translate").replace("{glossary}", glossary_text(load_glossary(course)))
    edits = Edits()
    done: list[str] = []

    # slides, in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_translate_slide, claude, system, u, lang): u for u in p.slides}
        for f in concurrent.futures.as_completed(futures):
            u = futures[f]
            try:
                f.result()
            except SourceError as e:
                diag.warn(u.slide.loc, f"slide '{u.slide.id}': {e.msg}")
                continue
            if u.result is None:
                diag.warn(u.slide.loc, f"slide '{u.slide.id}' niet vertaald; structuur klopt niet: "
                                       + "; ".join(u.errors))
                continue
            new = render_block(lang, src_hash(u.slide), u.result, u.labels_nl)
            nl, old = u.slide.langs[SOURCE_LANG], u.slide.langs.get(lang)
            path = nl.loc.file
            lines = path.read_text(encoding="utf-8").split("\n")
            if old is not None:
                end = _region_end(lines, old.loc.line, old.end)
                edits.replace(path, old.loc.line, end, new)
            else:
                end = _region_end(lines, nl.loc.line, nl.end)
                edits.replace(path, end, end, [""] + new)
            done.append(f"slide {u.slide.id}")

    # chapter headers
    for ch in p.headers:
        req = {"unit": "chapter_header", "target_language": lang,
               "title_nl": ch.title.get(SOURCE_LANG, ""),
               "keypoints_nl": [{"id": k, "text": v.get(SOURCE_LANG, "")} for k, v in ch.keypoints.items()]}
        try:
            result = claude.json(system, json.dumps(req, ensure_ascii=False), HEADER_SCHEMA)
        except SourceError as e:
            diag.warn(Loc(ch.path, 1), f"hoofdstukkop: {e.msg}")
            continue
        header_edits(ch, lang, result, edits, diag)
        done.append(f"hoofdstukkop {ch.id}")

    # quizzes, one request per chapter
    for ch, qs in p.quizzes:
        req = {"unit": "quiz", "target_language": lang, "questions": [
            {"id": str(i), "text": q.langs[SOURCE_LANG].text,
             "options": [o.text for o in q.langs[SOURCE_LANG].options],
             **({"previous_en": {"text": q.langs[lang].text,
                                 "options": [o.text for o in q.langs[lang].options]}}
                if lang in q.langs else {})}
            for i, q in enumerate(qs)]}
        try:
            result = claude.json(system, json.dumps(req, ensure_ascii=False), QUIZ_SCHEMA)
        except SourceError as e:
            diag.warn(Loc(ch.path, 1), f"quiz: {e.msg}")
            continue
        answers = {a["id"]: a for a in result["questions"]}
        for i, q in enumerate(qs):
            a, nl = answers.get(str(i)), q.langs[SOURCE_LANG]
            if a is None or len(a["options"]) != len(nl.options):
                diag.warn(q.loc, "quizvraag niet vertaald (aantal opties klopt niet)")
                continue
            new = [f"@{lang} src={question_hash(q)} {a['text'].strip()}"]
            new += [f"- [{'x' if o.correct else ' '}] {t.strip()}" for o, t in zip(nl.options, a["options"])]
            lines = nl.loc.file.read_text(encoding="utf-8").split("\n")
            old = q.langs.get(lang)
            if old is not None:
                edits.replace(old.loc.file, old.loc.line, _region_end(lines, old.loc.line, old.end), new)
            else:
                end = _region_end(lines, nl.loc.line, nl.end)
                edits.replace(nl.loc.file, end, end, new)
            done.append(f"quizvraag {ch.id}#{i + 1}")

    edits.apply()
    return done, claude.usage, claude.cfg["model"]
