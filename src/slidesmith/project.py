"""Loading courses and lessons from disk, and project-wide checks."""

from __future__ import annotations

from pathlib import Path

import yaml

from .model import Chapter, Course, Lesson, Loc, SOURCE_LANG
from .parser import Diagnostics, SourceError, lang_dict, parse_chapter, question_hash, src_hash

COURSE_FILE = "course.yaml"
LESSON_FILE = "lesson.yaml"

DEFAULT_CONFIG = {
    "langs": ["nl", "en"],
    "accent": "#F0A030",
    "logo": None,
    "logo_position": "bottom-right",
    "timebar": True,
    "wpm": {"nl": 140, "en": 150},
    "lessons_dir": "lessen",
}


def _load_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise SourceError(f"ongeldige YAML: {e}", Loc(path, 1)) from None
    if not isinstance(data, dict):
        raise SourceError("verwacht een YAML-mapping", Loc(path, 1))
    return data


def find_course_root(start: Path) -> Path:
    p = start.resolve()
    if p.is_file():
        p = p.parent
    for d in (p, *p.parents):
        if (d / COURSE_FILE).exists():
            return d
    raise SourceError(f"geen {COURSE_FILE} gevonden in {start} of bovenliggende mappen")


def load_lesson(path: Path, shared: Path, diag: Diagnostics) -> Lesson:
    cfg = _load_yaml(path / LESSON_FILE) if (path / LESSON_FILE).exists() else {}
    names = cfg.get("chapters") or sorted(p.name for p in path.glob("*.md"))
    chapters: list[Chapter] = []
    for name in names:
        f = path / name
        if not f.exists():
            raise SourceError(f"hoofdstuk niet gevonden: {name}", Loc(path / LESSON_FILE, 1))
        chapters.append(parse_chapter(f, shared, diag))
    return Lesson(
        id=str(cfg.get("id") or path.name),
        path=path.resolve(),
        title=lang_dict(cfg.get("title")) or {SOURCE_LANG: path.name},
        chapters=chapters,
    )


def load_course(start: Path, diag: Diagnostics | None = None,
                only: Path | None = None) -> Course:
    """Load the course containing `start`. With `only`, load just that lesson."""
    diag = diag if diag is not None else Diagnostics()
    root = find_course_root(start)
    raw = _load_yaml(root / COURSE_FILE)
    config = {**DEFAULT_CONFIG, **raw}
    config["wpm"] = {**DEFAULT_CONFIG["wpm"], **(raw.get("wpm") or {})}
    course = Course(
        root=root,
        title=lang_dict(raw.get("title")) or {SOURCE_LANG: root.name},
        langs=list(config["langs"]),
        config=config,
    )
    if raw.get("lessons"):
        lesson_dirs = [root / p for p in raw["lessons"]]
    else:
        base = root / config["lessons_dir"]
        lesson_dirs = sorted(p for p in base.iterdir() if p.is_dir()) if base.exists() else []
    if only is not None:
        only = only.resolve()
        lesson_dirs = [d for d in lesson_dirs if d.resolve() == only or d.resolve() in only.parents]
        if not lesson_dirs:
            raise SourceError(f"{only} hoort bij geen les van de cursus in {root}")
    for d in lesson_dirs:
        if not d.is_dir():
            raise SourceError(f"lesmap niet gevonden: {d}", Loc(root / COURSE_FILE, 1))
        course.lessons.append(load_lesson(d, course.shared, diag))
    return course


def check_translations(course: Course, diag: Diagnostics) -> None:
    """Warn about missing or outdated translations."""
    for lesson in course.lessons:
        for ch in lesson.chapters:
            for lang in course.langs:
                if lang == SOURCE_LANG:
                    continue
                if lang not in ch.title:
                    diag.warn(Loc(ch.path, 1), f"hoofdstuktitel mist '{lang}'")
                for kp, texts in ch.keypoints.items():
                    if lang not in texts:
                        diag.warn(Loc(ch.path, 1), f"keypoint '{kp}' mist '{lang}'")
                for s in ch.slides:
                    if SOURCE_LANG not in s.langs:
                        continue
                    want = src_hash(s)
                    b = s.langs.get(lang)
                    if b is None:
                        diag.warn(s.loc, f"slide '{s.id}': vertaling '{lang}' ontbreekt")
                    elif b.src != want:
                        diag.warn(b.loc, f"slide '{s.id}': vertaling '{lang}' is verouderd "
                                         f"(src={b.src}, NL is nu src={want})")
                for q in ch.quizzes:
                    for question in q.questions:
                        t = question.langs.get(lang)
                        want = question_hash(question)
                        if t is None:
                            diag.warn(question.loc, f"quizvraag: vertaling '{lang}' ontbreekt")
                        elif t.src != want:
                            diag.warn(question.loc,
                                      f"quizvraag: vertaling '{lang}' is verouderd (NL is nu src={want})")
