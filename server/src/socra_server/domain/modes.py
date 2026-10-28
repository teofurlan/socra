"""The modes of a project session: what each one tells the agent and which Socra tools it gets."""
from __future__ import annotations

import dataclasses
from typing import Literal

from socra_server.domain.speech import SPEECH_LANGUAGE_NAME

ModeId = Literal["mentor", "exam"]

SWITCH_MODE = "switch_mode"
SEARCH_TRANSCRIPT = "search_transcript"
RECORD_EXAM_RESULT = "record_exam_result"


class UnknownMode(ValueError):
    """The mode id is not one Socra offers."""


@dataclasses.dataclass(frozen=True)
class Mode:
    id: ModeId
    label: str
    # Appended to the backend's own system prompt for the whole session.
    instructions: str
    # Ids of the Socra tools the mode exposes (see socra_tools.TOOL_SPECS).
    tools: frozenset[str]


_COMMON = (
    "Socra is a voice layer: your replies are spoken aloud, so keep them short and plain. "
    f"Always reply in {SPEECH_LANGUAGE_NAME}: Socra listens and speaks only "
    f"{SPEECH_LANGUAGE_NAME}, so a message that reads like another language was misheard; "
    "ask the user to repeat it instead of switching language. "
    "When the user asks to switch between the mentor and exam modes, call the switch_mode "
    "tool; Socra asks the user to confirm on screen. If the notes you were given lack a "
    "detail, call search_transcript to look it up in the previous session."
)

MODES: dict[str, Mode] = {
    # Placeholder: the real mentor instructions belong to issue #18.
    "mentor": Mode(
        id="mentor",
        label="Mentor",
        instructions=(
            "You are a mentor. Explain the user's project and the code in it so they "
            "understand it. Read files as needed, but do not edit files or run commands "
            f"that change anything. {_COMMON}"
        ),
        tools=frozenset({SWITCH_MODE, SEARCH_TRANSCRIPT}),
    ),
    "exam": Mode(
        id="exam",
        label="Exam",
        instructions=(
            "You are examining the user orally about their project. Ask one question at a "
            "time, listen to the spoken answer, give brief spoken feedback, then ask the "
            "next. After grading each answer, call record_exam_result with the question, a "
            "verdict (correct, partial or incorrect) and a short note. Do not edit files. "
            f"{_COMMON}"
        ),
        tools=frozenset({SWITCH_MODE, SEARCH_TRANSCRIPT, RECORD_EXAM_RESULT}),
    ),
}

DEFAULT_MODE: ModeId = "mentor"


def get_mode(mode_id: str) -> Mode:
    mode = MODES.get(mode_id)
    if mode is None:
        raise UnknownMode(f"Unknown mode: {mode_id!r}")
    return mode
