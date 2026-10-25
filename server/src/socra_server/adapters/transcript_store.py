"""Session transcripts Socra keeps itself, as JSONL files outside the repository.

Layout: ``<root>/<project-hash>/<session-id>.jsonl``, one JSON object per turn.
Files older than ``RETENTION_DAYS`` are deleted when the server starts. A write that
fails is logged and dropped: a transcript must never break the conversation.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

RETENTION_DAYS = 30
SNIPPET_RADIUS = 100
DEFAULT_ROOT = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "Socra" / "sessions"
)


@dataclasses.dataclass(frozen=True)
class TranscriptHit:
    turn: int
    role: str
    snippet: str


class SessionTranscript:
    def __init__(self, path: Path, session_id: str) -> None:
        self.path = path
        self.session_id = session_id

    def append(self, role: str, text: str) -> None:
        record = {"t": time.time(), "role": role, "text": text}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        except (OSError, ValueError) as exc:
            logger.warning("Could not write the session transcript: %s", exc)

    def search(self, query: str, limit: int = 5) -> list[TranscriptHit]:
        needle = query.strip().lower()
        if not needle:
            return []
        try:
            lines = self.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return []
        hits: list[TranscriptHit] = []
        for number, line in enumerate(lines, start=1):
            try:
                record = json.loads(line)
                text = str(record["text"])
                role = str(record["role"])
            except (ValueError, KeyError, TypeError):
                continue
            at = text.lower().find(needle)
            if at == -1:
                continue
            start = max(0, at - SNIPPET_RADIUS)
            snippet = text[start : at + len(needle) + SNIPPET_RADIUS]
            hits.append(TranscriptHit(number, role, snippet))
            if len(hits) >= max(1, limit):
                break
        return hits


class TranscriptStore:
    def __init__(
        self, root: Path = DEFAULT_ROOT, *, now: Callable[[], float] = time.time
    ) -> None:
        self._root = Path(root)
        self._now = now

    def start(self, cwd: Path | str) -> SessionTranscript:
        identity = os.path.normcase(os.path.abspath(cwd))
        project = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        session_id = uuid.uuid4().hex
        return SessionTranscript(self._root / project / f"{session_id}.jsonl", session_id)

    def prune(self) -> int:
        """Delete transcripts past the retention; returns how many were removed."""
        cutoff = self._now() - RETENTION_DAYS * 86400
        removed = 0
        try:
            folders = [p for p in self._root.iterdir() if p.is_dir()]
        except OSError:
            return 0
        for folder in folders:
            for file in folder.glob("*.jsonl"):
                try:
                    if file.stat().st_mtime < cutoff:
                        file.unlink()
                        removed += 1
                except OSError as exc:
                    logger.warning("Could not prune %s: %s", file, exc)
            try:
                folder.rmdir()  # only succeeds when empty
            except OSError:
                pass
        return removed
