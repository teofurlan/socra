"""Pure rules of a narrated code walkthrough — no I/O.

A walkthrough is code plus ordered steps; each step is something to say and,
optionally, the 1-based inclusive line range it talks about.
"""
from __future__ import annotations

import dataclasses
import re
import unicodedata
from typing import Any, Literal

Command = Literal["pause", "resume", "repeat", "back", "next", "stop"]
# What the cursor does after a command: play the (new) current step, or end.
Outcome = Literal["play", "finished", "stopped"]


@dataclasses.dataclass(frozen=True)
class WalkthroughStep:
    say: str
    lines: tuple[int, int] | None = None


@dataclasses.dataclass(frozen=True)
class Walkthrough:
    code: str
    language: str
    steps: tuple[WalkthroughStep, ...]


def _error(step: int | None, field: str, message: str) -> dict:
    return {"step": step, "field": field, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_lines(raw: Any, line_count: int, number: int) -> tuple[tuple[int, int] | None, dict | None]:
    field = "focus.lines"
    lines = raw.get("lines") if isinstance(raw, dict) else None
    if not (isinstance(lines, (list, tuple)) and len(lines) == 2 and all(_is_int(n) for n in lines)):
        return None, _error(number, field, "focus.lines must be [start, end], two whole numbers")
    start, end = lines
    if start < 1:
        return None, _error(number, field, f"lines start at 1, got {start}")
    if end < start:
        return None, _error(number, field, f"end line {end} is before its start {start}")
    if end > line_count:
        return None, _error(number, field, f"lines {start}-{end} are outside the code, which only has {line_count} lines")
    return (start, end), None


def parse_walkthrough(code: Any, language: Any, steps: Any) -> tuple[Walkthrough | None, list[dict]]:
    """Validate client input. Returns the walkthrough, or every problem found."""
    errors: list[dict] = []
    if not isinstance(code, str) or not code.strip():
        errors.append(_error(None, "code", "code must be a non-empty string"))
        line_count = 0
    else:
        line_count = len(code.removesuffix("\n").split("\n"))
    if not isinstance(steps, (list, tuple)) or not steps:
        errors.append(_error(None, "steps", "steps must be a non-empty list"))
        steps = []

    parsed: list[WalkthroughStep] = []
    for number, raw in enumerate(steps, start=1):
        if not isinstance(raw, dict):
            errors.append(_error(number, "step", "a step must be an object with say and focus"))
            continue
        say = raw.get("say")
        valid = True
        if not isinstance(say, str) or not say.strip():
            errors.append(_error(number, "say", "say must be a non-empty string"))
            valid = False
        lines = None
        if raw.get("focus") is not None:
            lines, problem = _parse_lines(raw["focus"], line_count, number)
            if problem:
                errors.append(problem)
                valid = False
        if valid:
            parsed.append(WalkthroughStep(say=say.strip(), lines=lines))

    if errors:
        return None, errors
    return Walkthrough(code=code, language=language if isinstance(language, str) else "", steps=tuple(parsed)), []


# ---------------------------------------------------------------------------
# Spoken commands
# ---------------------------------------------------------------------------

_PHRASES: dict[Command, tuple[str, ...]] = {
    "pause": ("pause", "wait", "hold on", "pausa", "espera", "un momento"),
    "repeat": ("repeat", "repeat that", "repeat it", "again", "say that again", "say it again",
               "repite", "repetir", "otra vez", "de nuevo", "repitelo"),
    "back": ("back", "go back", "previous", "previous step", "step back",
             "atras", "anterior", "vuelve", "volver", "paso anterior"),
    "next": ("next", "next step", "skip", "skip this", "go next",
             "siguiente", "adelante", "salta", "paso siguiente"),
    "resume": ("continue", "resume", "go on", "keep going", "carry on", "go ahead",
               "continua", "continuar", "sigue", "seguir", "reanuda"),
    "stop": ("stop", "stop it", "end", "thats enough", "enough", "done", "quit",
             "para", "parar", "detente", "basta", "ya esta", "ya basta", "termina"),
}


_POLITE = {"please", "por", "favor"}


def _normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.replace("'", "").replace("’", "")
    words = re.sub(r"[^a-z0-9]+", " ", folded).split()
    return " ".join(w for w in words if w not in _POLITE)


_LOOKUP = {_normalize(phrase): command for command, phrases in _PHRASES.items() for phrase in phrases}


def parse_command(text: str) -> Command | None:
    """Map a whole utterance to a walkthrough command; anything else is not one."""
    return _LOOKUP.get(_normalize(text) or "")


# ---------------------------------------------------------------------------
# Step cursor
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class StepCursor:
    """Which step is current; moves on commands, never past the ends."""

    total: int
    index: int = 0

    def advance(self) -> Outcome:
        """The current step finished playing on its own."""
        return self.apply("next")

    def apply(self, command: Command) -> Outcome:
        if command == "stop":
            return "stopped"
        if command == "next":
            if self.index + 1 >= self.total:
                return "finished"
            self.index += 1
        elif command == "back":
            self.index = max(0, self.index - 1)
        return "play"
