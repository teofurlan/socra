"""Split a streaming Markdown reply into pieces that can be spoken one by one.

Speech starts sooner when each complete sentence becomes its own clip while the
agent is still writing. The splitter is incremental and pure: ``feed`` takes the
next chunk of text and returns the pieces that are now complete; ``flush``
returns whatever is left (a tool call started or the reply ended).

Pieces are raw Markdown. Run ``speakable_text`` on each one so code and Markdown markers
are not read aloud. Fenced code blocks are never split inside; they come out as
one piece of their own, so the sentence before a block is not held back.
"""
from __future__ import annotations

import re

_TERMINATORS = ".!?…"
_CLOSERS = "\"'”’)]»*_`"
_FENCES = ("```", "~~~")
_BLANK_LINE = re.compile(r"\n[ \t]*\n")
# A new list item or heading on the next line ends the current piece.
_BLOCK_START = re.compile(r"\n[ \t]*(?:[-*+]|\d{1,3}[.)]|#{1,6})[ \t]")
_ABBREVIATIONS = frozenset({
    "mr", "mrs", "ms", "dr", "prof", "sr", "sra", "srta", "dra", "vs", "e.g", "i.e",
    "fig", "approx", "cf", "st", "jr", "no", "pág", "pag", "núm", "ej",
})
# Ends a sentence only when a capitalised word follows; otherwise it is mid-sentence.
_SOFT_STOPS = frozenset({"etc"})
_NEW_SENTENCE_OPENERS = "¿¡\"“(["


class SentenceSplitter:
    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[str]:
        """Add text; return the pieces that are complete now, in order."""
        self._buffer += text
        pieces: list[str] = []
        while True:
            self._buffer = self._buffer.lstrip()
            end = _piece_end(self._buffer)
            if end is None:
                return pieces
            piece, self._buffer = self._buffer[:end].strip(), self._buffer[end:]
            if piece:
                pieces.append(piece)

    def flush(self) -> list[str]:
        """Return the unfinished remainder as one piece, leaving the splitter empty."""
        rest, self._buffer = self._buffer.strip(), ""
        return [rest] if rest else []


def split_sentences(text: str) -> list[str]:
    """Split a complete text; the same result as feeding it to a SentenceSplitter."""
    splitter = SentenceSplitter()
    return splitter.feed(text) + splitter.flush()


def _piece_end(buffer: str) -> int | None:
    """Where the first piece of ``buffer`` ends, or None while it is still open."""
    if buffer.startswith(_FENCES):
        return _fence_end(buffer)
    i = 0
    length = len(buffer)
    while i < length:
        char = buffer[i]
        at_line_start = i == 0 or buffer[i - 1] == "\n"
        if at_line_start and buffer.startswith(_FENCES, i):
            return i
        if char == "\n":
            blank = _BLANK_LINE.match(buffer, i)
            if blank:
                return blank.end()
            if _BLOCK_START.match(buffer, i):
                return i
        elif char in _TERMINATORS:
            decision = _sentence_stop(buffer, i)
            if decision is _WAIT:
                return None
            if isinstance(decision, int):
                return decision
            i = decision.resume
            continue
        i += 1
    return None


class _Wait:
    pass


class _Skip:
    def __init__(self, resume: int) -> None:
        self.resume = resume


_WAIT = _Wait()


def _fence_end(buffer: str) -> int | None:
    """End of a fenced block: a line made only of the opening marker (at least as long)."""
    char = buffer[0]
    opening = len(buffer) - len(buffer.lstrip(char))
    close = re.compile(rf"\n[ \t]*{re.escape(char)}{{{opening},}}[ \t]*\n")
    first_line_end = buffer.find("\n")
    if first_line_end == -1:
        return None
    match = close.search(buffer, first_line_end)
    return None if match is None else match.end()


def _sentence_stop(buffer: str, start: int) -> int | _Skip | _Wait:
    """Decide whether the terminator run at ``start`` ends a sentence."""
    end = start
    while end < len(buffer) and buffer[end] in _TERMINATORS:
        end += 1
    run = buffer[start:end]
    while end < len(buffer) and buffer[end] in _CLOSERS:
        end += 1
    if end >= len(buffer):
        return _WAIT  # cannot tell yet: "memoria." may still become "memoria.txt"
    if not buffer[end].isspace():
        return _Skip(end)
    if "…" in run or run.startswith(".") and len(run) > 1:
        return _stop_before_capital(buffer, end)
    if run == ".":
        word_start = max(buffer.rfind(" ", 0, start), buffer.rfind("\n", 0, start)) + 1
        word = buffer[word_start:start].lstrip("([\"'“")
        lowered = word.lower()
        if lowered in _SOFT_STOPS:
            return _stop_before_capital(buffer, end)
        if lowered in _ABBREVIATIONS:
            return _Skip(end)
        if len(word) == 1 and word.isalpha() and word.isupper():
            return _Skip(end)  # an initial such as "J. Smith"
        if word.isdigit() and len(word) <= 3 and (word_start == 0 or buffer[word_start - 1] == "\n"):
            return _Skip(end)  # a list number such as "1."
    return end


def _stop_before_capital(buffer: str, end: int) -> int | _Skip | _Wait:
    follow = end
    while follow < len(buffer) and buffer[follow].isspace():
        follow += 1
    if follow >= len(buffer):
        return _WAIT
    next_char = buffer[follow]
    if next_char.isupper() or next_char in _NEW_SENTENCE_OPENERS or next_char.isdigit():
        return end
    return _Skip(end)
