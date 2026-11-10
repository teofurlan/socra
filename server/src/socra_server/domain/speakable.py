"""Turn an agent's Markdown reply into plain text worth speaking aloud.

The page shows the full reply; speech skips what only sounds like noise when a
TTS voice reads it: code blocks, Markdown markers, the folders of a file path,
the rest of a URL after its site name, and commit hashes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_FENCED_CODE = re.compile(r"(```|~~~).*?(?:\1|\Z)", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# Markers can compose (for example, a list inside a quote). Up to three digits
# keeps a year opening a line from being taken for a list number.
_LINE_MARKER = re.compile(r"^\s*(?:(?:#{1,6}|[-*+]|\d{1,3}[.)])\s+|>\s?)+", re.MULTILINE)
# Markers only at word edges, so snake_case, 2**10 and a*b survive. "__x__"
# is left alone: it reads the same as a dunder name such as __init__.
_EMPHASIS = tuple(
    re.compile(rf"(?<!\w){marker}(?![\s*_])(.+?)(?<![\s*_]){marker}(?!\w)")
    for marker in (r"\*\*", r"\*", "_")
)

# A URL ends before trailing punctuation that closes the sentence around it.
_URL_END = r"[^\s<>]*?>?(?=[.,;:!?)\]]*(?:\s|$))"
_URL = re.compile(rf"<?(?<![\w@./])(?:https?://|www\.)(?P<host>[^\s/<>?#]+){_URL_END}", re.IGNORECASE)
# "github.com/owner/repo" without a scheme: a dotted host followed by a path.
_BARE_URL = re.compile(
    rf"(?<![\w@./\\-])(?P<host>(?:[a-z0-9-]+\.)+[a-z]{{2,}})/{_URL_END}", re.IGNORECASE
)
_SECOND_LEVEL = frozenset({"ac", "co", "com", "edu", "gov", "net", "org"})

_SEPARATOR = re.compile(r"[\\/]")
_PATH = re.compile(
    r"(?<![\w@./\\:-])(?P<root>[A-Za-z]:[\\/]|~[\\/]|\.{1,2}[\\/]|[\\/])?[\w@+.-]*(?:[\\/][\w@+.-]*)*"
)
_EXTENSION = re.compile(r"[^.]\.[A-Za-z][A-Za-z0-9]{0,9}$")

# Git prints hashes in lowercase. Requiring a digit and a letter keeps plain
# numbers (1234567) and words made of a to f (effaced) in the speech.
_COMMIT_HASH = re.compile(
    r"[ \t]*(?<![\w./-])(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}(?![\w/-])"
)


@dataclass
class SpokenPaths:
    """The file paths one reply has mentioned, keyed by the name speech uses.

    Pass the same instance for every piece of one reply: a file name shared by
    two different paths is then spoken with its folder ("web app"). A piece
    already spoken cannot change, so only later mentions gain the folder.
    """

    _by_name: dict[str, set[str]] = field(default_factory=dict)

    def add(self, name: str, key: str) -> None:
        self._by_name.setdefault(name, set()).add(key)

    def clashes(self, name: str) -> bool:
        return len(self._by_name.get(name, ())) > 1


@dataclass(frozen=True)
class _Path:
    name: str
    folder: str
    key: str
    trailing: str


def speakable_text(markdown: str, paths: SpokenPaths | None = None) -> str:
    text = _FENCED_CODE.sub(" ", markdown)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _URL.sub(lambda m: _site_name(m["host"]), text)
    text = _BARE_URL.sub(lambda m: _site_name(m["host"]), text)
    text = _speak_paths(text, SpokenPaths() if paths is None else paths)
    text = _COMMIT_HASH.sub("", text)
    text = _LINE_MARKER.sub("", text)
    for pattern in _EMPHASIS:
        text = pattern.sub(r"\1", text)
    return " ".join(text.split())


def _site_name(host: str) -> str:
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].lower()
    labels = [label for label in host.split(".") if label]
    if not labels or all(label.isdigit() for label in labels):
        return host  # an IP address has no site name
    if labels[0] == "www" and len(labels) > 1:
        labels = labels[1:]
    if len(labels) > 1:
        top = labels.pop()
        if len(labels) > 1 and len(top) == 2 and labels[-1] in _SECOND_LEVEL:
            labels.pop()  # bbc.co.uk
    return labels[-1]


def _speak_paths(text: str, paths: SpokenPaths) -> str:
    found = [(match, _parse_path(match)) for match in _PATH.finditer(text)]
    for _, path in found:
        if path is not None:
            paths.add(path.name, path.key)

    def spoken(match: re.Match[str]) -> str:
        path = _parse_path(match)
        if path is None:
            return match[0]
        name = f"{path.folder} {path.name}" if path.folder and paths.clashes(path.name) else path.name
        return name + path.trailing

    return _PATH.sub(spoken, text)


def _parse_path(match: re.Match[str]) -> _Path | None:
    """The spoken parts of a path, or None when the match is ordinary text (and/or, 1/2)."""
    raw = match[0]
    core = raw.rstrip(".")
    trailing = raw[len(core):]
    if not _SEPARATOR.search(core):
        return None
    segments = [s for s in _SEPARATOR.split(core) if s and s not in {".", "..", "~"}]
    if match["root"] and match["root"][0].isalpha():
        segments = segments[1:]  # the drive letter of C:\
    if not segments:
        return None
    is_directory = core[-1] in "\\/"
    last = segments[-1]
    looks_like_path = bool(match["root"]) or "\\" in core or is_directory or _EXTENSION.search(last)
    if not looks_like_path:
        return None
    name = last if is_directory else last.lstrip(".").split(".")[0] or last
    folder = segments[-2] if len(segments) > 1 else ""
    return _Path(name=name, folder=folder, key="/".join(segments), trailing=trailing)
