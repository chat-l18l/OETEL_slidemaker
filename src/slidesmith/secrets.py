"""API keys: from the environment, or from ~/.config/slidesmith/secrets.env (outside the repo)."""

from __future__ import annotations

import os
from pathlib import Path

SECRETS_FILE = Path.home() / ".config" / "slidesmith" / "secrets.env"


def get(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    if SECRETS_FILE.exists():
        for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == name and not key.startswith("#"):
                return value.strip().strip('"').strip("'")
    return None
