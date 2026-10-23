"""Pure domain types for agent mode — no I/O and no backend-specific names."""
from __future__ import annotations

import dataclasses
from typing import Literal

BackendState = Literal["ready", "not_configured", "unreachable"]


@dataclasses.dataclass(frozen=True)
class AgentSelection:
    """What the user picks and the page persists: a backend and one of its models."""

    backend: str
    model: str


@dataclasses.dataclass(frozen=True)
class ModelOption:
    id: str
    label: str


@dataclasses.dataclass(frozen=True)
class BackendStatus:
    """Whether a backend can run now; ``message`` explains anything but ready."""

    state: BackendState
    message: str = ""

    @property
    def ready(self) -> bool:
        return self.state == "ready"


@dataclasses.dataclass(frozen=True)
class BackendInfo:
    """A backend as shown in the selector."""

    id: str
    label: str
    models: list[ModelOption]
    status: BackendStatus
    supports_modes: bool = False


@dataclasses.dataclass(frozen=True)
class PermissionRequest:
    """A tool call the backend's own rules want the user to approve."""

    request_id: str
    tool: str
    title: str
    detail: str = ""


# --------------------------------------------------------------------------- #
# Events streamed while the agent answers one turn                             #
# --------------------------------------------------------------------------- #

@dataclasses.dataclass(frozen=True)
class TextDelta:
    """A piece of the reply text, in order."""

    text: str


@dataclasses.dataclass(frozen=True)
class ToolActivity:
    """The agent is using a tool; shown on the page, never spoken."""

    tool: str
    summary: str = ""
    # File the tool acts on, when it names one; Socra records it as a fact.
    path: str = ""


@dataclasses.dataclass(frozen=True)
class ReplyDone:
    """The turn finished; ``text`` is the full final reply."""

    text: str


@dataclasses.dataclass(frozen=True)
class AgentError:
    """The turn failed; the conversation may still accept another turn."""

    message: str


AgentEvent = TextDelta | ToolActivity | ReplyDone | AgentError
