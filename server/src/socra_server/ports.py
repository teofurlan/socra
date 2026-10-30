"""Port protocols — pure interfaces; no implementation details."""
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from socra_server.domain.agent import (
    AgentEvent,
    BackendStatus,
    ModelOption,
    PermissionRequest,
)
from socra_server.domain.modes import Mode


@runtime_checkable
class SpeechSynthesizer(Protocol):
    """Synthesize text to WAV bytes."""

    def synthesize(self, text: str) -> bytes:
        """Return raw WAV bytes for the given text."""
        ...


@runtime_checkable
class SpeechRecognizer(Protocol):
    """Transcribe WAV bytes to text."""

    def transcribe(self, wav_bytes: bytes, prompt: str = "") -> str:
        """Return verbatim transcript.  Empty string when audio is silent."""
        ...


class PermissionDecider(Protocol):
    """Ask the user about a tool call; True allows it, False denies it."""

    async def __call__(self, request: PermissionRequest) -> bool:
        ...


@runtime_checkable
class AgentConversation(Protocol):
    """One agent session in one working folder."""

    def send(self, text: str) -> AsyncIterator[AgentEvent]:
        """Send one user turn and stream its events until ReplyDone or AgentError."""
        ...

    async def interrupt(self) -> None:
        """Stop the turn in progress, if any."""
        ...

    async def close(self) -> None:
        ...


class SocraToolbox(Protocol):
    """What Socra's own tools do inside an agent session (see ``socra_tools``)."""

    async def switch_mode(self, target: str) -> str:
        """Ask the user to confirm a switch to ``target``; returns text for the agent."""
        ...

    async def record_exam_result(self, question: str, verdict: str, note: str) -> str:
        ...

    async def search_transcript(self, query: str, limit: int) -> list[Any]:
        """Hits (``turn``, ``role``, ``snippet``) from the previous session's transcript."""
        ...

    async def present(self, scene: Any) -> str:
        """Play a narrated scene on the page; returns how it ended, as text for the agent."""
        ...


@runtime_checkable
class AgentBackend(Protocol):
    """An agent Socra can drive (Claude Code first; Pi or a direct API later)."""

    id: str
    label: str
    # True when ``open`` honours ``mode`` and ``toolbox`` (instructions plus Socra tools).
    supports_modes: bool

    def models(self) -> list[ModelOption]:
        ...

    async def check(self) -> BackendStatus:
        """Report whether the backend can run now, without starting a session."""
        ...

    async def open(
        self,
        model: str,
        cwd: Path,
        decide_permission: PermissionDecider,
        *,
        mode: Mode | None = None,
        toolbox: SocraToolbox | None = None,
    ) -> AgentConversation:
        """Start a conversation; ``decide_permission`` answers tool calls that need approval.

        ``mode`` and ``toolbox`` are passed only when ``supports_modes`` is true.
        """
        ...
