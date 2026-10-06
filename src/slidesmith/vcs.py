"""Version information from git, hg or svn, for title pages of printed material."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Version:
    system: str  # git | hg | svn | ""
    rev: str
    date: str
    dirty: bool = False

    def __str__(self) -> str:
        if not self.system:
            return "geen versiebeheer"
        return f"{self.system} {self.rev}{' (gewijzigd)' if self.dirty else ''}, {self.date}"


def _run(cmd: list[str], cwd: Path) -> str | None:
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def version(path: Path) -> Version:
    if (rev := _run(["git", "describe", "--always", "--tags", "--dirty=+"], path)) is not None:
        dirty = rev.endswith("+")
        date = _run(["git", "log", "-1", "--format=%cs"], path) or ""
        return Version("git", rev.rstrip("+"), date, dirty)
    if (rev := _run(["hg", "id", "-i"], path)) is not None:
        date = _run(["hg", "log", "-r", ".", "--template", "{date|shortdate}"], path) or ""
        return Version("hg", rev.rstrip("+"), date, rev.endswith("+"))
    if (rev := _run(["svnversion", "."], path)) and rev[0].isdigit():
        date = (_run(["svn", "info", "--show-item", "last-changed-date"], path) or "")[:10]
        return Version("svn", "r" + rev.rstrip("M"), date, rev.endswith("M"))
    return Version("", "", "")
