"""Fix near misses of known words in a transcript, by how they sound (no model call).

Whisper is already primed with the known terms, but it still writes "socrá", "Zocra"
or "web socket". Each run of one to three words is compared with every known term
through a rough phonetic key (accents, case, spacing and letters that sound alike are
ignored); an exact key match is replaced by the term as written. A single word that is
merely similar is never replaced, so real words ("sobra") survive.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

MAX_WORDS = 3
MIN_KEY_LENGTH = 4  # shorter keys ("pr", "pi") match too many ordinary words

# Mishearings no phonetic rule can bridge (an English name heard as another English word).
ALIASES: dict[str, str] = {
    "cloud code": "Claude Code",
}

_WORD = re.compile(r"\w+")
_SOUNDS = (
    ("ph", "f"), ("qu", "k"), ("ch", "x"), ("sh", "x"), ("ll", "y"),
)


def sound_key(text: str) -> str:
    """A rough phonetic key: 'Sócra', 'socra', 'Zokra' and 'so cra' share one."""
    folded = unicodedata.normalize("NFD", text.lower())
    key = "".join(ch for ch in folded if unicodedata.category(ch) != "Mn")
    key = re.sub(r"[^a-z0-9]", "", key)
    for written, sound in _SOUNDS:
        key = key.replace(written, sound)
    key = re.sub(r"c(?=[ei])", "s", key)
    key = key.translate(str.maketrans({"c": "k", "q": "k", "z": "s", "v": "b", "w": "u", "h": None}))
    return re.sub(r"(.)\1+", r"\1", key)


def correct_terms(text: str, terms: Iterable[str]) -> str:
    """Return ``text`` with near misses of ``terms`` written as the terms; earlier terms win."""
    known = [(term, term) for term in terms]
    if not known or not text:
        return text
    index: dict[str, str] = {}
    for heard_as, term in [*known, *ALIASES.items()]:
        key = sound_key(heard_as)
        if len(key) >= MIN_KEY_LENGTH:
            index.setdefault(key, term)

    words = list(_WORD.finditer(text))
    pieces: list[str] = []
    cursor = 0
    i = 0
    while i < len(words):
        match = _longest_match(text, words, i, index)
        if match is None:
            i += 1
            continue
        count, term = match
        start, end = words[i].start(), words[i + count - 1].end()
        heard = text[start:end]
        if not _same_term(heard, term):
            pieces.append(text[cursor:start])
            pieces.append(term)
            cursor = end
        i += count
    pieces.append(text[cursor:])
    return "".join(pieces)


def _longest_match(text: str, words: list[re.Match[str]], i: int, index: dict[str, str]) -> tuple[int, str] | None:
    for count in range(min(MAX_WORDS, len(words) - i), 0, -1):
        run = words[i:i + count]
        # Words join only across plain spaces, never across punctuation.
        if any(text[a.end():b.start()].strip() for a, b in zip(run, run[1:])):
            continue
        term = index.get(sound_key("".join(w.group() for w in run)))
        if term is not None:
            return count, term
    return None


def _same_term(heard: str, term: str) -> bool:
    """Already right: written the same, or a lowercase term heard with other capitals."""
    return heard == term or (term == term.lower() and heard.lower() == term)
