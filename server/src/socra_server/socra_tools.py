"""Socra's own tools for an agent session, defined once for every backend that can host them.

A ``ToolSpec`` is backend-neutral: an id, a description, a JSON schema and a handler that
talks to a ``SocraToolbox``. A backend adapter wraps the specs its mode lists. To add a tool
(for example the narrated walkthrough), append a spec to ``TOOL_SPECS`` and list its id in
the modes that expose it (``domain/modes.py``).
"""
from __future__ import annotations

import dataclasses
from collections.abc import Awaitable, Callable
from typing import Any

from socra_server.domain.modes import (
    CLEAR_SCENE,
    POINT_AT,
    PRESENT,
    RECORD_EXAM_RESULT,
    REPLAY_STEP,
    SCENE_GUIDE_TOOL,
    SHOW_RESULT,
    SEARCH_TRANSCRIPT,
    SWITCH_MODE,
    Mode,
)
from socra_server.domain.scene import PRESENT_PURPOSE, PRESENT_SUMMARY
from socra_server.domain.scene_guide import TOPICS, scene_guide
from socra_server.ports import SocraToolbox

VERDICTS = ("correct", "partial", "incorrect")
SEARCH_LIMIT = 5
ToolHandler = Callable[[SocraToolbox, dict[str, Any]], Awaitable[str]]


@dataclasses.dataclass(frozen=True)
class ToolSpec:
    id: str
    description: str
    schema: dict[str, Any]
    handler: ToolHandler


async def _switch_mode(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    return await toolbox.switch_mode(str(args.get("mode", "")))


async def _record_exam_result(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    verdict = str(args.get("verdict", ""))
    if verdict not in VERDICTS:
        return "The verdict must be one of: correct, partial or incorrect."
    return await toolbox.record_exam_result(
        str(args.get("question", "")), verdict, str(args.get("note", ""))
    )


async def _search_transcript(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    limit = args.get("limit")
    hits = await toolbox.search_transcript(
        str(args.get("query", "")), limit if isinstance(limit, int) and limit > 0 else SEARCH_LIMIT
    )
    if not hits:
        return "No matches in the previous session's transcript."
    return "\n".join(f"turn {h.turn} ({h.role}): {h.snippet}" for h in hits)


async def _present(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    return await toolbox.present(args.get("scene"))


async def _clear_scene(toolbox: SocraToolbox, _args: dict[str, Any]) -> str:
    return await toolbox.clear_scene()


async def _point_at(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    return await toolbox.point_at(args.get("targets"))


async def _show_result(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    return await toolbox.show_result(args)


async def _replay_step(toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    return await toolbox.replay_step(args)


async def _scene_guide(_toolbox: SocraToolbox, args: dict[str, Any]) -> str:
    topic = args.get("topic")
    return scene_guide(topic if isinstance(topic, str) else "")


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        SWITCH_MODE,
        "Ask to switch this project session to another mode. Use it when the user asks to "
        "be examined or to be mentored, or to go back to coding. Socra shows the user a "
        "confirmation and switches only if they accept, so say you asked and wait.",
        {
            "type": "object",
            "properties": {"mode": {"type": "string", "enum": ["agent", "mentor", "exam"]}},
            "required": ["mode"],
        },
        _switch_mode,
    ),
    ToolSpec(
        SEARCH_TRANSCRIPT,
        "Search the previous session's transcript for a word or phrase when the handoff "
        "notes lack a detail.",
        {
            "type": "object",
            "properties": {"query": {"type": "string"}, "limit": {"type": "integer"}},
            "required": ["query"],
        },
        _search_transcript,
    ),
    ToolSpec(
        RECORD_EXAM_RESULT,
        "Record the verdict on one answer to an exam or check question after grading it.",
        {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "verdict": {"type": "string", "enum": list(VERDICTS)},
                "note": {"type": "string"},
            },
            "required": ["question", "verdict"],
        },
        _record_exam_result,
    ),
    ToolSpec(
        SCENE_GUIDE_TOOL,
        "Call before present. Returns how to write a narrated scene (rules, format, primitives) "
        "and an example. topic is code to explain a module, flow or function of the project, or "
        "concept to explain a programming concept.",
        {
            "type": "object",
            "properties": {"topic": {"type": "string", "enum": list(TOPICS)}},
            "required": ["topic"],
        },
        _scene_guide,
    ),
    ToolSpec(
        PRESENT,
        f"{PRESENT_PURPOSE} {PRESENT_SUMMARY}",
        {
            "type": "object",
            "properties": {"scene": {"type": "object", "description": "The narrated scene to play."}},
            "required": ["scene"],
        },
        _present,
    ),
    ToolSpec(
        CLEAR_SCENE,
        "Removes the finished scene from the user's screen. Call it when the check after a "
        "scene ends or is declined. A scene that is still playing is not removed.",
        {"type": "object", "properties": {}},
        _clear_scene,
    ),
    ToolSpec(
        POINT_AT,
        "Highlights objects of the finished scene on the user's screen while you ask about them. "
        "Call it right before asking each check question; an empty list removes the highlight. "
        "Object ids must be code, diagram or structure objects of the scene you presented. Parts: a diagram node id; in a "
        "structure cell:<index>, bucket:<b>, entry:<b>:<pos> or node:<key>; code uses lines "
        "[start, end] (1-based). Invalid targets come back as errors and nothing is highlighted.",
        {
            "type": "object",
            "properties": {
                "targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "object": {"type": "string", "description": "Id of an object of the scene"},
                            "part": {"type": "string", "description": "Optional part of the object"},
                            "lines": {
                                "type": "array", "items": {"type": "integer"},
                                "minItems": 2, "maxItems": 2,
                                "description": "Code only: [start, end] line range",
                            },
                        },
                        "required": ["object"],
                    },
                },
            },
            "required": ["targets"],
        },
        _point_at,
    ),
    ToolSpec(
        SHOW_RESULT,
        "Shows the real outcome of one operation on a structure of the finished scene, animated on "
        "the user's screen, for a prediction question. Ask the question first (point_at the structure, "
        "say what will be done, e.g. insert 12), wait for the answer, then call this and grade the "
        "answer against the outcome text it returns. object is the structure's id; op is an "
        "operation like a scene cue uses for that kind: array set {index, value}, swap or compare "
        "{indexes}, highlight {indexes}; stack push {value} or pop; queue enqueue {value} or "
        "dequeue; hashTable and tree insert, lookup {key} (also remove for hashTable, highlight "
        "for tree). It applies to what is on screen now, so calls chain. Invalid input comes back "
        "as errors and nothing is shown.",
        {
            "type": "object",
            "properties": {
                "object": {"type": "string", "description": "Id of a structure object of the scene"},
                "op": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "description": 'Operation name, e.g. "insert"'},
                        "params": {"type": "object", "description": 'Its params, e.g. {"key": 12}'},
                    },
                    "required": ["action"],
                },
            },
            "required": ["object", "op"],
        },
        _show_result,
    ),
    ToolSpec(
        REPLAY_STEP,
        "Goes over one step of the finished scene again: its picture is shown again and you say a NEW "
        "short explanation of it. Use it when the user accepts your offer to see the related step "
        "again after a miss. step is a step id of the scene (an unknown id comes back with the valid "
        "ones). say is required: what you will say, written for what this user got wrong, never the "
        "step's original words (that is rejected). targets, optional, highlights the part they "
        "confused, same shape as point_at, checked before anything plays. Returns once it has "
        "played, or stopped.",
        {
            "type": "object",
            "properties": {
                "step": {"type": "string", "description": "Id of a step of the scene"},
                "say": {"type": "string", "description": "Your new short explanation, aimed at the user's mistake"},
                "targets": {
                    "type": "array",
                    "description": "Optional objects to highlight, same shape as point_at targets",
                    "items": {"type": "object"},
                },
            },
            "required": ["step", "say"],
        },
        _replay_step,
    ),
)


def specs_for(mode: Mode) -> list[ToolSpec]:
    return [spec for spec in TOOL_SPECS if spec.id in mode.tools]


@dataclasses.dataclass
class CallbackToolbox:
    """A toolbox built from async callbacks, so the app wires it without a subclass."""

    switch: Callable[[str], Awaitable[str]]
    record: Callable[[str, str, str], Awaitable[str]]
    search: Callable[[str, int], Awaitable[list[Any]]]
    play: Callable[[Any], Awaitable[str]]
    clear: Callable[[], Awaitable[str]]
    point: Callable[[Any], Awaitable[str]]
    show: Callable[[Any], Awaitable[str]]
    replay: Callable[[Any], Awaitable[str]]

    async def switch_mode(self, target: str) -> str:
        return await self.switch(target)

    async def record_exam_result(self, question: str, verdict: str, note: str) -> str:
        return await self.record(question, verdict, note)

    async def search_transcript(self, query: str, limit: int) -> list[Any]:
        return await self.search(query, limit)

    async def present(self, scene: Any) -> str:
        return await self.play(scene)

    async def clear_scene(self) -> str:
        return await self.clear()

    async def point_at(self, targets: Any) -> str:
        return await self.point(targets)

    async def show_result(self, args: Any) -> str:
        return await self.show(args)

    async def replay_step(self, args: Any) -> str:
        return await self.replay(args)
