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
    RECORD_EXAM_RESULT,
    SEARCH_TRANSCRIPT,
    SWITCH_MODE,
    Mode,
)
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


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        SWITCH_MODE,
        "Ask to switch this project session to another mode. Use it when the user asks to "
        "be examined, mentored or to go back to coding. Socra shows the user a confirmation "
        "and switches only if they accept, so say you asked and wait.",
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
        "Record the verdict on one exam answer after grading it.",
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
)


def specs_for(mode: Mode) -> list[ToolSpec]:
    return [spec for spec in TOOL_SPECS if spec.id in mode.tools]


@dataclasses.dataclass
class CallbackToolbox:
    """A toolbox built from three async callbacks, so the app wires it without a subclass."""

    switch: Callable[[str], Awaitable[str]]
    record: Callable[[str, str, str], Awaitable[str]]
    search: Callable[[str, int], Awaitable[list[Any]]]

    async def switch_mode(self, target: str) -> str:
        return await self.switch(target)

    async def record_exam_result(self, question: str, verdict: str, note: str) -> str:
        return await self.record(question, verdict, note)

    async def search_transcript(self, query: str, limit: int) -> list[Any]:
        return await self.search(query, limit)
