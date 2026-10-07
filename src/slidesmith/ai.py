"""Claude calls for the AI commands (translate, review, draft, quiz).

One place for the client, model choice, structured JSON output, refusal handling and
cost bookkeeping. Prompts live as text files in `prompts/`, so Claude Code and the CLI
follow the same rules.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path

from . import secrets
from .model import Course
from .parser import SourceError

PROMPTS = Path(__file__).parent / "prompts"
DEFAULT_AI = {"model": "claude-opus-5-5", "effort": "medium"}
# USD per million tokens: input, output, cache read, cache write (5 min)
PRICES = {"claude-opus-5-5": (4.00, 20.00, 0.20, 5.00)}


def ai_config(course: Course) -> dict:
    return {**DEFAULT_AI, **(course.config.get("ai") or {})}


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8")


@dataclass
class Usage:
    requests: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, u) -> None:
        with self._lock:
            self.requests += 1
            self.input += u.input_tokens or 0
            self.output += u.output_tokens or 0
            self.cache_read += getattr(u, "cache_read_input_tokens", 0) or 0
            self.cache_write += getattr(u, "cache_creation_input_tokens", 0) or 0

    def cost(self, model: str) -> float | None:
        p = PRICES.get(model)
        if p is None:
            return None
        return (self.input * p[0] + self.output * p[1] + self.cache_read * p[2]
                + self.cache_write * p[3]) / 1_000_000

    def summary(self, model: str) -> str:
        c = self.cost(model)
        money = f", ca. ${c:.3f}" if c is not None else ""
        return (f"{self.requests} verzoeken, {self.input + self.cache_read + self.cache_write:,} tokens in "
                f"({self.cache_read:,} uit cache), {self.output:,} uit{money}").replace(",", ".")


class Claude:
    def __init__(self, course: Course):
        try:
            import anthropic
        except ImportError:
            raise SourceError("het pakket 'anthropic' ontbreekt (pixi install)") from None
        key = secrets.get("ANTHROPIC_API_KEY")
        if not key:
            raise SourceError("ANTHROPIC_API_KEY ontbreekt (omgeving of ~/.config/slidesmith/secrets.env)")
        headers = {}
        if ws := secrets.get("ANTHROPIC_WORKSPACE_ID"):
            headers["anthropic-workspace-id"] = ws
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=key, default_headers=headers or None, max_retries=4)
        self.cfg = ai_config(course)
        self.usage = Usage()

    def json(self, system: str, user: str, schema: dict, max_tokens: int = 16000) -> dict:
        """One request with a JSON-schema constrained answer. The system prompt is cached."""
        a = self.anthropic
        try:
            r = self.client.beta.messages.create(
                model=self.cfg["model"],
                max_tokens=max_tokens,
                # server-side fallback: if a safety classifier declines, another model answers
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                output_config={"effort": self.cfg["effort"],
                               "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": user}],
            )
        except a.AuthenticationError:
            raise SourceError("Anthropic: ongeldige API-key") from None
        except a.PermissionDeniedError as e:
            raise SourceError(f"Anthropic: geen toegang ({e.message})") from None
        except a.BadRequestError as e:
            msg = e.message
            if "workspace" in msg:
                msg += "\n  → zet ANTHROPIC_WORKSPACE_ID in ~/.config/slidesmith/secrets.env"
            raise SourceError(f"Anthropic: {msg}") from None
        except a.RateLimitError:
            raise SourceError("Anthropic: rate limit, probeer het later opnieuw") from None
        except a.APIStatusError as e:
            raise SourceError(f"Anthropic {e.status_code}: {e.message}") from None
        except a.APIConnectionError:
            raise SourceError("Anthropic: geen verbinding") from None
        self.usage.add(r.usage)
        if r.stop_reason == "refusal":
            raise SourceError("Anthropic weigerde dit verzoek (ook na fallback)")
        if r.stop_reason == "max_tokens":
            raise SourceError("Anthropic: antwoord afgekapt (max_tokens)")
        text = next((b.text for b in r.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            raise SourceError("Anthropic gaf geen geldige JSON terug") from None
