"""`slides review`: content review of chapters, as a report with file:line locations.

Two layers: fixed checks (free, instant) and a review by Claude per chapter. Claude's
findings are cached on a hash of the chapter content, prompt and model, so unchanged
chapters cost nothing on the next run (useful in a git hook or CI). The review never
edits the source.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from . import ai
from .model import Chapter, Course, Loc, Slide, SOURCE_LANG
from .parser import Diagnostics, SourceError
from .translate import glossary_text, load_glossary, slide_labels

SEVERITIES = ("error", "warning", "suggestion")
DEFAULT_REVIEW = {"max_words": 40, "max_bullets": 6, "max_line_chars": 60}

FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "slide_id": {"type": "string"},
            "field": {"type": "string", "enum": ["body", "script", "reader", "notes", "labels", "quiz", "chapter"]},
            "severity": {"type": "string", "enum": list(SEVERITIES)},
            "category": {"type": "string", "enum": [
                "spelling", "terminology", "script-slide", "tts", "density", "clarity",
                "keypoint", "correctness", "quiz"]},
            "quote": {"type": "string"},
            "message": {"type": "string"},
            "suggestion": {"type": "string"},
        },
        "required": ["slide_id", "field", "severity", "category", "quote", "message", "suggestion"],
        "additionalProperties": False}}},
    "required": ["findings"],
    "additionalProperties": False,
}


@dataclass
class Finding:
    file: str
    line: int
    severity: str
    category: str
    message: str
    suggestion: str = ""
    slide_id: str = ""
    source: str = "check"  # check | claude

    def text(self) -> str:
        s = f"{self.file}:{self.line}: [{self.severity}] {self.category}: {self.message}"
        if self.suggestion:
            s += f"\n    → {self.suggestion}"
        return s


# ---------------------------------------------------------------- locating text

def _lines(path: Path, cache: dict[Path, list[str]]) -> list[str]:
    if path not in cache:
        cache[path] = path.read_text(encoding="utf-8").split("\n")
    return cache[path]


def field_line(slide: Slide, lang: str, field: str, quote: str, files: dict) -> tuple[Path, int]:
    """Best source line for a finding: the line containing the quote, else the field's directive."""
    b = slide.langs.get(lang) or slide.langs.get(SOURCE_LANG)
    loc = b.loc if b and b.loc else slide.loc
    lines = _lines(loc.file, files)
    end = (b.end if b and b.end else len(lines) + 1)
    start = loc.line
    if field == "labels" and slide.diagram:
        start = slide.loc.line  # labels also live in the shared part
    q = " ".join(quote.split())
    if q:
        for n in range(start, end):
            if q in " ".join(lines[n - 1].split()):
                return loc.file, n
    marker = {"script": "@script", "reader": "@reader", "notes": "@notes", "labels": "@labels"}.get(field)
    if marker:
        for n in range(loc.line, end):
            if lines[n - 1].startswith(marker):
                return loc.file, n
    return loc.file, (loc.line + 1 if field == "body" else loc.line)


# ---------------------------------------------------------------- fixed checks

_FENCE = re.compile(r"^\s*(```|~~~)")


def body_text_lines(body: str) -> list[str]:
    """Visible prose lines of a slide body: no code blocks, math blocks, tables or directives."""
    out, in_code = [], False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_code = not in_code
            continue
        if in_code or line.startswith(("|", "@col", "$$")) or not line.strip():
            continue
        out.append(line)
    return out


def fixed_checks(course: Course, ch: Chapter, lang: str, files: dict) -> list[Finding]:
    cfg = {**DEFAULT_REVIEW, **(course.config.get("review") or {})}
    out: list[Finding] = []
    root = course.root

    def add(slide, field, quote, severity, category, message, suggestion=""):
        path, line = field_line(slide, lang, field, quote, files)
        out.append(Finding(str(_rel(path, root)), line, severity, category, message, suggestion, slide.id))

    for s in ch.slides:
        b = s.langs.get(lang)
        if b is None:
            continue
        lines = body_text_lines(b.body)
        prose = [re.sub(r"^#+\s*|^[-*+]\s+|^\d+[.)]\s+|^=>\s*|^>\s*", "", x) for x in lines]
        words = sum(len(re.findall(r"\w+", re.sub(r"\$[^$]*\$|`[^`]*`|\]\([^)]*\)", "", x))) for x in prose)
        if s.layout not in ("code", "table") and words > cfg["max_words"]:
            add(s, "body", "", "warning", "density",
                f"{words} woorden op de slide (maximum {cfg['max_words']}); verplaats uitleg naar @script of @reader")
        bullets = sum(1 for x in lines if re.match(r"^(?:[-*+]|\d+[.)])\s", x))
        if bullets > cfg["max_bullets"]:
            add(s, "body", "", "warning", "density", f"{bullets} bullets (maximum {cfg['max_bullets']})")
        for x, p in zip(lines, prose):
            # bullets and takeaways should fit on one line; quotes and subtitles may wrap
            if re.match(r"^(?:[-*+]|\d+[.)]|=>)\s", x) and len(p) > cfg["max_line_chars"]:
                add(s, "body", x.strip(), "suggestion", "density",
                    f"regel van {len(p)} tekens (maximum {cfg['max_line_chars']}); wordt op de slide afgebroken")

    used = {kp for s in ch.slides for kp in s.keypoints}
    quizzed = {q.keypoint for qz in ch.quizzes for q in qz.questions if q.keypoint}
    for kp in ch.keypoints:
        if kp not in used:
            out.append(Finding(str(_rel(ch.path, root)), 1, "warning", "keypoint",
                               f"keypoint '{kp}' wordt door geen enkele slide behandeld (keypoints=…)"))
        elif kp not in quizzed:
            out.append(Finding(str(_rel(ch.path, root)), 1, "suggestion", "keypoint",
                               f"keypoint '{kp}' wordt niet overhoord in een quizvraag"))
    return out


def _rel(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root.parent)
    except ValueError:
        return path


# ---------------------------------------------------------------- Claude review

def visible_labels(s: Slide, lang: str) -> dict[str, str]:
    """All diagram/callout labels as shown in `lang` (inline label.<lang> or @labels overrides)."""
    labels = {k: v for k, v in slide_labels(s).items()}
    for c in s.callouts:
        labels[c.id] = c.label.get(lang) or c.label.get(SOURCE_LANG, "")
    b = s.langs.get(lang)
    if b is not None:
        labels.update(b.labels)
    return labels


def chapter_payload(ch: Chapter, lang: str) -> dict:
    slides = []
    for s in ch.slides:
        b = s.langs.get(lang)
        if b is None:
            continue
        item = {"slide_id": s.id, "layout": s.layout, "keypoints": s.keypoints,
                "body": b.body, "script": b.script, "reader": b.reader, "notes": b.notes,
                "labels": visible_labels(s, lang)}
        if s.diagram and s.diagram.kind != "boxes":
            item["diagram"] = {"kind": s.diagram.kind, "source": s.diagram.source}
        if s.image:
            item["image"] = s.image.path.name
        slides.append(item)
    quiz = []
    for qz in ch.quizzes:
        for q in qz.questions:
            t = q.langs.get(lang)
            if t:
                quiz.append({"keypoint": q.keypoint, "question": t.text,
                             "options": [{"text": o.text, "correct": o.correct} for o in t.options]})
    return {"language": lang, "chapter": ch.title.get(lang) or ch.title.get(SOURCE_LANG, ""),
            "keypoints": {k: v.get(lang) or v.get(SOURCE_LANG, "") for k, v in ch.keypoints.items()},
            "slides": slides, "quiz": quiz}


def _cache_key(payload: dict, system: str, cfg: dict) -> str:
    raw = json.dumps([payload, system, cfg], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:20]


def claude_review(claude: ai.Claude, system: str, ch: Chapter, lang: str, cache_dir: Path) -> tuple[list[dict], bool]:
    """Findings from Claude for one chapter; (findings, from_cache)."""
    payload = chapter_payload(ch, lang)
    key = _cache_key(payload, system, claude.cfg)
    cached = cache_dir / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8")), True
    result = claude.json(system, json.dumps(payload, ensure_ascii=False, indent=1), FINDINGS_SCHEMA)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(result["findings"], ensure_ascii=False, indent=1), encoding="utf-8")
    return result["findings"], False


def to_findings(raw: list[dict], ch: Chapter, lang: str, root: Path, files: dict) -> list[Finding]:
    by_id = {s.id: s for s in ch.slides}
    out = []
    for f in raw:
        s = by_id.get(f["slide_id"])
        if s is not None:
            path, line = field_line(s, lang, f["field"], f["quote"], files)
        else:
            path, line = ch.path, 1
            if f["field"] == "quiz" and ch.quizzes:
                path, line = ch.quizzes[0].loc.file, ch.quizzes[0].loc.line
                lines = _lines(path, files)
                q = " ".join(f["quote"].split())
                for n in range(line, len(lines) + 1):
                    if q and q in " ".join(lines[n - 1].split()):
                        line = n
                        break
        out.append(Finding(str(_rel(path, root)), line, f["severity"], f["category"], f["message"],
                           f["suggestion"], f["slide_id"], "claude"))
    return out


# ---------------------------------------------------------------- main

@dataclass
class Report:
    findings: list[Finding]
    usage: ai.Usage | None
    model: str
    cached: int
    reviewed: int

    def count(self, severity: str) -> int:
        return sum(1 for f in self.findings if f.severity == severity)

    def as_json(self) -> str:
        return json.dumps([asdict(f) for f in self.findings], ensure_ascii=False, indent=1)

    def as_markdown(self, title: str) -> str:
        out = [f"# Review: {title}", ""]
        for sev in SEVERITIES:
            group = [f for f in self.findings if f.severity == sev]
            if not group:
                continue
            out += [f"## {sev} ({len(group)})", ""]
            for f in group:
                out.append(f"- `{f.file}:{f.line}` **{f.category}**: {f.message}")
                if f.suggestion:
                    out.append(f"  → {f.suggestion}")
            out.append("")
        return "\n".join(out)


def run(course: Course, lang: str, diag: Diagnostics, ids: set[str] | None = None,
        use_ai: bool = True, cache_dir: Path | None = None) -> Report:
    files: dict[Path, list[str]] = {}
    chapters = [ch for lesson in course.lessons for ch in lesson.chapters]
    if ids:
        chapters = [ch for ch in chapters if ch.id in ids or any(s.id in ids for s in ch.slides)]
    findings: list[Finding] = []
    for ch in chapters:
        findings += fixed_checks(course, ch, lang, files)

    usage, model, cached = None, "", 0
    if use_ai and chapters:
        claude = ai.Claude(course)
        system = ai.prompt("review").replace("{glossary}", glossary_text(load_glossary(course)))
        cache_dir = cache_dir or course.root / "build" / ".cache" / "review"
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(claude_review, claude, system, ch, lang, cache_dir): ch for ch in chapters}
            for f in concurrent.futures.as_completed(futures):
                ch = futures[f]
                try:
                    raw, from_cache = f.result()
                except SourceError as e:
                    diag.warn(Loc(ch.path, 1), f"review van hoofdstuk '{ch.id}' mislukt: {e.msg}")
                    continue
                cached += from_cache
                if ids:
                    raw = [x for x in raw if x["slide_id"] in ids or ch.id in ids]
                findings += to_findings(raw, ch, lang, course.root, files)
        usage, model = claude.usage, claude.cfg["model"]

    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (order[f.severity], f.file, f.line))
    return Report(findings, usage, model, cached, len(chapters))
