"""Command line interface: `slides build | serve | check`."""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from .build import build
from .model import Course, SOURCE_LANG
from .parser import Diagnostics, SourceError
from .project import check_translations, find_course_root, load_course

YELLOW, RED, DIM, RESET = "\033[33m", "\033[31m", "\033[2m", "\033[0m"


def _color(code: str, text: str) -> str:
    return f"{code}{text}{RESET}" if sys.stderr.isatty() else text


def _print_warnings(diag: Diagnostics) -> None:
    for loc, msg in diag.warnings:
        where = f"{loc}: " if loc else ""
        print(_color(YELLOW, "waarschuwing: ") + where + msg, file=sys.stderr)


def _load(path: Path, diag: Diagnostics) -> Course:
    root = find_course_root(path)
    only = None if path.resolve() == root else path
    return load_course(root, diag, only=only)


def _langs(arg: str | None, course: Course) -> list[str]:
    if not arg:
        return course.langs
    langs = arg.split(",")
    for lang in langs:
        if lang not in course.langs:
            raise SourceError(f"taal '{lang}' staat niet in course.yaml (langs: {course.langs})")
    return langs


def cmd_build(args) -> int:
    diag = Diagnostics()
    t0 = time.perf_counter()
    course = _load(args.path, diag)
    out = (args.out or course.root / "build").resolve()
    written = build(course, out, _langs(args.lang, course), diag)
    check_translations(course, diag)
    _print_warnings(diag)
    for p in written:
        print(_color(DIM, "  geschreven ") + str(p.relative_to(out.parent)))
    print(f"klaar in {time.perf_counter() - t0:.2f}s → {out}")
    return 0


def cmd_pdf(args) -> int:
    from .pdf import build_pdfs

    diag = Diagnostics()
    t0 = time.perf_counter()
    course = _load(args.path, diag)
    out = (args.out or course.root / "build").resolve()
    kinds = args.kind.split(",")
    for k in kinds:
        if k not in ("slides", "reader"):
            raise SourceError(f"onbekend PDF-soort '{k}' (slides, reader)")
    written = build_pdfs(course, out, _langs(args.lang, course), kinds, diag)
    _print_warnings(diag)
    for p in written:
        print(_color(DIM, "  geschreven ") + str(p.relative_to(out.parent)))
    print(f"klaar in {time.perf_counter() - t0:.1f}s")
    return 0


def cmd_video(args) -> int:
    from .video import build_lesson_video

    def confirm(chars: int, quota: tuple[int, int] | None) -> bool:
        left = f"; tegoed nog {quota[1] - quota[0]:,} van {quota[1]:,}" if quota else ""
        print(f"TTS: {chars:,} tekens te synthetiseren{left}".replace(",", "."), file=sys.stderr)
        if args.yes:
            return True
        if not sys.stdin.isatty():
            print("geen terminal om te bevestigen; gebruik --yes", file=sys.stderr)
            return False
        return input("doorgaan? [j/N] ").strip().lower() in ("j", "ja", "y", "yes")

    diag = Diagnostics()
    t0 = time.perf_counter()
    course = _load(args.path, diag)
    out = (args.out or course.root / "build").resolve()
    subs = args.subs.split(",") if args.subs else None
    written = []
    for lang in _langs(args.lang, course):
        for lesson in course.lessons:
            written += build_lesson_video(course, lesson, lang, out, diag, confirm,
                                          silent=args.silent, sub_langs=subs)
    _print_warnings(diag)
    for p in written:
        print(_color(DIM, "  geschreven ") + str(p.relative_to(out.parent)))
    print(f"klaar in {time.perf_counter() - t0:.1f}s")
    return 0


def cmd_translate(args) -> int:
    from . import translate

    def confirm(plan) -> bool:
        items = plan.describe()
        print(f"te vertalen ({len(items)}):", file=sys.stderr)
        for line in items:
            print(f"  {line}", file=sys.stderr)
        if args.dry_run:
            return False
        if args.yes:
            return True
        if not sys.stdin.isatty():
            print("geen terminal om te bevestigen; gebruik --yes", file=sys.stderr)
            return False
        return input("doorgaan? [j/N] ").strip().lower() in ("j", "ja", "y", "yes")

    diag = Diagnostics()
    t0 = time.perf_counter()
    course = _load(args.path, diag)
    ids = set(args.id) if args.id else None
    langs = [lang for lang in _langs(args.lang, course) if lang != SOURCE_LANG]
    for lang in langs:
        try:
            done, usage, model = translate.run(course, lang, diag, ids, args.force, confirm)
        except SourceError as e:
            if args.dry_run and e.msg == "gestopt":
                continue
            raise
        if not done:
            print(f"{lang}: niets te vertalen")
            continue
        for d in done:
            print(_color(DIM, f"  {lang} vertaald ") + d)
        print(f"{lang}: {len(done)} onderdelen; {usage.summary(model)}")
        course = _load(args.path, Diagnostics())
    check_translations(course, diag)
    _print_warnings(diag)
    print(f"klaar in {time.perf_counter() - t0:.1f}s; bekijk de wijzigingen met 'git diff'")
    return 0


def cmd_check(args) -> int:
    diag = Diagnostics()
    course = _load(args.path, diag)
    with tempfile.TemporaryDirectory() as tmp:
        build(course, Path(tmp), course.langs, diag)
    check_translations(course, diag)
    _print_warnings(diag)
    n = sum(len(ch.slides) for lesson in course.lessons for ch in lesson.chapters)
    print(f"{n} slides gecontroleerd, {len(diag.warnings)} waarschuwing(en)")
    return 1 if (args.strict and diag.warnings) else 0


def cmd_stamp(args) -> int:
    from .translations import stamp

    diag = Diagnostics()
    course = _load(args.path, diag)
    ids = set(args.id) if args.id else None
    for lang in _langs(args.lang, course):
        if lang == SOURCE_LANG:
            continue
        for loc, h in stamp(course, lang, ids):
            print(f"{loc}: {lang} src={h}")
    return 0


def cmd_serve(args) -> int:
    from . import server

    course_root = find_course_root(args.path)
    out = (args.out or course_root / "build").resolve()

    def rebuild() -> str | None:
        diag = Diagnostics()
        t0 = time.perf_counter()
        try:
            course = _load(args.path, diag)
            build(course, out, _langs(args.lang, course), diag, live=args.port + 1)
        except SourceError as e:
            print(_color(RED, "fout: ") + str(e), file=sys.stderr)
            return str(e)
        _print_warnings(diag)
        print(_color(DIM, f"herbouwd in {time.perf_counter() - t0:.2f}s"))
        return None

    worker = server.make_worker()
    err = worker.submit(rebuild).result()
    course = load_course(course_root)
    lang = (args.lang or course.langs[0]).split(",")[0]
    print(f"\nserveer {out}")
    print(f"  cursus:  http://{args.host}:{args.port}/{lang}/index.html")
    for lesson in course.lessons:
        print(f"  les:     http://{args.host}:{args.port}/{lang}/{lesson.id}.html")
    print("  (S = sprekersnotities, Esc = overzicht, Ctrl+C = stoppen)")
    if err:
        print(_color(RED, "let op: eerste build faalde; pas de bron aan, de pagina herlaadt vanzelf"))
    server.run(course_root, out, args.host, args.port, rebuild, worker)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="slides", description="Slides als code: bouw presentaties uit tekstbestanden.")
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("path", nargs="?", type=Path, default=Path("."),
                        help="cursusmap, lesmap of hoofdstukbestand (standaard: .)")
        sp.add_argument("--lang", help="talen, kommagescheiden (standaard: alle uit course.yaml)")
        sp.add_argument("--out", type=Path, help="uitvoermap (standaard: <cursus>/build)")

    sp = sub.add_parser("build", help="bouw HTML-presentaties")
    common(sp)
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("pdf", help="bouw PDF's (slides en/of reader) in het printthema")
    common(sp)
    sp.add_argument("--kind", default="slides,reader", help="slides, reader of beide (standaard)")
    sp.set_defaults(func=cmd_pdf)

    sp = sub.add_parser("video", help="conceptvideo met TTS-stem, ondertitels en YouTube-hoofdstukken")
    common(sp)
    sp.add_argument("--yes", action="store_true", help="niet vragen vóór betaalde TTS-synthese")
    sp.add_argument("--silent", action="store_true", help="zonder TTS: geschatte timing, geen audio")
    sp.add_argument("--subs", help="talen voor ondertitels, kommagescheiden (standaard: alle)")
    sp.set_defaults(func=cmd_video)

    sp = sub.add_parser("translate", help="vertaal ontbrekende/verouderde onderdelen met Claude")
    common(sp)
    sp.add_argument("--id", action="append", help="alleen deze slide- of quiz-id (herhaalbaar)")
    sp.add_argument("--force", action="store_true", help="ook bijgewerkte onderdelen opnieuw vertalen")
    sp.add_argument("--dry-run", action="store_true", help="alleen tonen wat vertaald zou worden")
    sp.add_argument("--yes", action="store_true", help="niet om bevestiging vragen")
    sp.set_defaults(func=cmd_translate)

    sp = sub.add_parser("serve", help="bouw, serveer en herlaad automatisch bij wijzigingen")
    common(sp)
    sp.add_argument("--host", default="127.0.0.1")
    sp.add_argument("--port", type=int, default=8000, help="HTTP-poort (websocket = poort+1)")
    sp.set_defaults(func=cmd_serve)

    sp = sub.add_parser("check", help="controleer bron, verwijzingen en vertalingen")
    common(sp)
    sp.add_argument("--strict", action="store_true", help="exit-code 1 bij waarschuwingen (voor CI/hooks)")
    sp.set_defaults(func=cmd_check)

    sp = sub.add_parser("stamp", help="markeer vertalingen als bijgewerkt t.o.v. de NL-bron (na review)")
    common(sp)
    sp.add_argument("--id", action="append", help="alleen deze slide- of quiz-id (herhaalbaar)")
    sp.set_defaults(func=cmd_stamp)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except SourceError as e:
        print(_color(RED, "fout: ") + str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
