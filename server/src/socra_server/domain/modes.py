"""The modes of a project session: what each one tells the agent and which Socra tools it gets."""
from __future__ import annotations

import dataclasses
from typing import Literal

from socra_server.domain.speech import SPEECH_LANGUAGE_NAME

ModeId = Literal["mentor", "exam"]

SWITCH_MODE = "switch_mode"
SEARCH_TRANSCRIPT = "search_transcript"
RECORD_EXAM_RESULT = "record_exam_result"
PRESENT = "present"
CLEAR_SCENE = "clear_scene"
POINT_AT = "point_at"
SCENE_GUIDE_TOOL = "scene_guide"


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
    # Closing instruction of the handoff seed when the user said nothing during the switch.
    opening: str
    # What to do after answering words the user said during the switch ("" = nothing more).
    after_pending: str = ""


_SCENE_CHECK = (
    "After present returns completed, offer by voice a short check of 2 or 3 questions about "
    "what the scene showed; never force it. If the user accepts, ask one question at a time, "
    "give brief spoken feedback (correct, partial or incorrect) and call record_exam_result "
    "after grading each answer. Before asking each question, call point_at with the scene objects "
    "it is about; call it with an empty list when the question is not about anything specific. "
    "When the check ends or the user declines, call clear_scene and continue the conversation "
    "normally. "
)

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
            "understand it. Read files as needed with the file reading and search tools, "
            "not shell commands, and do not edit files or run commands "
            f"that change anything. When an explanation is about structure, a flow or data (how a "
            "module or a request works in this project, a data structure or an algorithm), show "
            "it: call scene_guide, then present a scene; otherwise just talk. "
            f"{_SCENE_CHECK}"
            f"{_COMMON}"
        ),
        tools=frozenset(
            {SWITCH_MODE, SEARCH_TRANSCRIPT, RECORD_EXAM_RESULT, SCENE_GUIDE_TOOL, PRESENT, CLEAR_SCENE, POINT_AT}
        ),
        opening=(
            "Now say, in one spoken sentence, what you understand the situation to be, "
            "so the user can correct you. Do not start any work yet."
        ),
    ),
    "exam": Mode(
        id="exam",
        label="Exam",
        instructions=(
            "You are examining the user orally about their project. Ask one question at a "
            "time, listen to the spoken answer, give brief spoken feedback, then ask the "
            "next. After grading each answer, call record_exam_result with the question, a "
            "verdict (correct, partial or incorrect) and a short note. Do not edit files. "
            "To show the code or diagram a question refers to, call scene_guide then present; "
            "never show the answer. "
            f"{_SCENE_CHECK}"
            f"{_COMMON}"
        ),
        tools=frozenset(
            {SWITCH_MODE, SEARCH_TRANSCRIPT, RECORD_EXAM_RESULT, SCENE_GUIDE_TOOL, PRESENT, CLEAR_SCENE, POINT_AT}
        ),
        opening=(
            "Start the exam now: ask the first question right away, with at most a very short "
            "lead-in, grounded in the context carried over above. Do not restate the situation."
        ),
        after_pending=(
            " Then continue the exam: ask the first question if you have not asked it yet."
        ),
    ),
}

DEFAULT_MODE: ModeId = "mentor"


def get_mode(mode_id: str) -> Mode:
    mode = MODES.get(mode_id)
    if mode is None:
        raise UnknownMode(f"Unknown mode: {mode_id!r}")
    return mode
