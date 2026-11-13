"""Slash commands in spoken form: "barra tdd arregla esto" is the command "/tdd arregla esto"."""
from __future__ import annotations

import re
from collections.abc import Iterable

from socra_server.domain.vocabulary import sound_key

_SPOKEN = re.compile(r"^\s*(?:b[aá]rra|slash)\b[\s,.:;]*(?P<rest>.+?)\s*$", re.IGNORECASE | re.DOTALL | re.UNICODE)
_WORD = re.compile(r"[^\s,.:;]+")
_MAX_NAME_WORDS = 4


def spoken_command(text: str, names: Iterable[str]) -> str:
    """Return ``text`` as "/name rest" when it starts with "barra"/"slash" followed by a known
    command's name (compared by sound, so "slash TDD" and "barra t d d" both work); else as heard."""
    spoken = _SPOKEN.match(text)
    if spoken is None:
        return text
    by_sound = {}
    for name in names:
        key = sound_key(name)
        if key:
            by_sound.setdefault(key, name)
    if not by_sound:
        return text
    rest = spoken.group("rest")
    words = list(_WORD.finditer(rest))
    # The longest run of words wins: "code review" before "code".
    for count in range(min(_MAX_NAME_WORDS, len(words)), 0, -1):
        heard = " ".join(match.group() for match in words[:count])
        name = by_sound.get(sound_key(heard))
        if name is not None:
            argument = rest[words[count - 1].end():].lstrip(" ,.:;\t\r\n")
            return f"/{name} {argument}" if argument else f"/{name}"
    return text

