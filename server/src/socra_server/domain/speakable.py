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

# URL patterns are greedy and leave trailing punctuation to the code, so they stay
# linear on long runs of dots or commas.
_URL = re.compile(r"<?(?<![\w@./])(?:https?://|www\.)(?P<host>[^\s/<>?#]+)[^\s<>]*>?", re.IGNORECASE)
# "github.com/owner/repo" without a scheme: a lowercase host on a common top-level
# domain, so Node.js/Deno, ASP.NET/Core or main.py/utils.py are not taken for sites.
_BARE_URL = re.compile(
    r"(?<![\w@./\\-])(?P<host>(?:[a-z0-9-]+\.)+(?:"
    r"com|org|net|io|dev|app|ai|edu|gov|info|me|sh|xyz|co|uk|ar|es|mx|cl|uy|br|de|fr|it"
    r"))/[^\s<>]*"
)
_URL_TRAILING = ".,;:!?)]"
_SECOND_LEVEL = frozenset({"ac", "co", "com", "edu", "gov", "net", "org"})

_SEPARATOR = re.compile(r"[\\/]")
_PATH = re.compile(
    r"(?<![\w@./\\:-])(?P<root>[A-Za-z]:[\\/]|~[\\/]|\.{1,2}[\\/]|[\\/])?[\w@+.-]*(?:[\\/][\w@+.-]*)*"
)
# An extension after a name (app.py) or a dotfile (.gitignore).
_EXTENSION = re.compile(r"(?:^|[^.])\.[A-Za-z][A-Za-z0-9]{0,9}$")
# A dotted name such as Node.js or main.py: as a folder, it is one of a pair of names.
_DOTTED_NAME = re.compile(r"[^.]\.[A-Za-z]{1,10}$")

# Git prints hashes in lowercase. Requiring a digit and a letter keeps plain
# numbers (1234567) and words made of a to f (effaced) in the speech; a hash in
# brackets goes with them. A "#" before it is a colour, 1000000e7 a number.
_COMMIT_HASH = re.compile(
    r"[ \t]?(?<![\w./#-])(?P<open>\()?(?![0-9]+e[0-9]+(?![\w/-]))"
    r"(?=[0-9a-f]{0,39}[0-9])(?=[0-9a-f]{0,39}[a-f])[0-9a-f]{7,40}(?(open)\))(?![\w/-])"
)


@dataclass(frozen=True)
class _Path:
    segments: tuple[str, ...]  # folders, then the file (or last folder) as written
    name: str  # what speech says when no other path clashes
    trailing: str  # dots after the path that end the sentence


@dataclass
class SpokenPaths:
    """The file paths one reply has mentioned, grouped by the name speech uses.

    Pass the same instance for every piece of one reply. When two different
    paths share a name, each is said with what tells it apart: its extension
    when that differs (index.ts, index.css), otherwise as many folders as needed
    (server app, web app). A piece already spoken cannot change, so only later
    mentions gain the difference.
    """

    _by_name: dict[str, set[tuple[str, ...]]] = field(default_factory=dict)

    def add(self, path: _Path) -> None:
        self._by_name.setdefault(path.name, set()).add(path.segments)

    def spoken(self, path: _Path) -> str:
        others = self._by_name.get(path.name, set()) - {path.segments}
        if not others:
            return path.name
        last = path.segments[-1]
        same_file = [other for other in others if other[-1] == last]
        if not same_file:
            return last.lstrip(".")
        folders = path.segments[:-1]
        depth = 1
        while depth < len(folders) and any(
            other[-depth - 1:-1] == folders[-depth:] for other in same_file
        ):
            depth += 1
        return " ".join((*folders[len(folders) - depth:], path.name))


def speakable_text(markdown: str, paths: SpokenPaths | None = None) -> str:
    text = _FENCED_CODE.sub(" ", markdown)
    text = _INLINE_CODE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _LINE_MARKER.sub("", text)
    for pattern in _EMPHASIS:
        text = pattern.sub(r"\1", text)
    text = _URL.sub(_spoken_url, text)
    text = _BARE_URL.sub(_spoken_url, text)
    text = _speak_paths(text, SpokenPaths() if paths is None else paths)
    text = _COMMIT_HASH.sub("", text)
    return " ".join(text.split())


def _spoken_url(match: re.Match[str]) -> str:
    url = match[0]
    site = _site_name(match["host"])
    if url.startswith("<") and url.endswith(">"):
        return site
    return site + url[len(url.rstrip(_URL_TRAILING)):]


def _site_name(host: str) -> str:
    host = host.rsplit("@", 1)[-1].split(":", 1)[0].rstrip(_URL_TRAILING).lower()
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
    for match in _PATH.finditer(text):
        path = _parse_path(match)
        if path is not None:
            paths.add(path)

    def spoken(match: re.Match[str]) -> str:
        path = _parse_path(match)
        return match[0] if path is None else paths.spoken(path) + path.trailing

    return _PATH.sub(spoken, text)


def _parse_path(match: re.Match[str]) -> _Path | None:
    """The spoken parts of a path, or None when the match is ordinary text (and/or, 1/2)."""
    raw = match[0]
    core = raw.rstrip(".")
    trailing = raw[len(core):]
    if not _SEPARATOR.search(core):
        return None
    segments = [s for s in _SEPARATOR.split(core) if s and s not in {".", "..", "~"}]
    if any(s.endswith(".") for s in segments):
        return None  # abbreviations such as e.g./i.e., not folders
    root = match["root"]
    if root and root[0].isalpha():
        segments = segments[1:]  # the drive letter of C:\
    if not segments:
        return None
    if not root and any(_DOTTED_NAME.search(s) for s in segments[:-1]):
        return None  # a pair of names such as Node.js/Deno or main.py/utils.py
    is_directory = core[-1] in "\\/"
    last = segments[-1]
    looks_like_path = bool(root) or "\\" in core or is_directory or _EXTENSION.search(last)
    if not looks_like_path:
        return None
    name = last if is_directory else last.lstrip(".").split(".")[0] or last
    return _Path(segments=tuple(segments), name=name, trailing=trailing)
