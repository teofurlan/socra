"""What a mode switch carries over: recorded facts, a validated summary and the last turns."""
from __future__ import annotations

import dataclasses
import json
import re
from collections import Counter

from socra_server.domain.agent import ToolActivity
from socra_server.domain.modes import Mode

VERBATIM_TURNS = 4
REPLY_CAP = 1500
# Tools whose path argument is a file the session changed.
FILE_TOOLS = frozenset({"Edit", "Write", "MultiEdit", "NotebookEdit"})
SUMMARY_FIELDS = ("goal", "decisions", "open_items", "user_doubts")

SUMMARY_PROMPT = (
    "Socra is about to continue this work in a fresh session. Write a handoff summary now, "
    "without using any tools. Reply with only a JSON object with these keys: "
    '"goal" (string, what we are trying to do), "decisions" (list of strings, what was '
    'decided), "open_items" (list of strings, what is still to do) and "user_doubts" '
    "(list of strings, what the user was unsure about). Use an empty list when there is "
    "nothing to report."
)


class InvalidSummary(ValueError):
    """The outgoing agent's summary lacks fields; ``missing`` names them."""

    def __init__(self, missing: list[str]) -> None:
        super().__init__(f"Summary is missing: {', '.join(missing)}")
        self.missing = missing


@dataclasses.dataclass(frozen=True)
class HandoffSummary:
    goal: str
    decisions: list[str]
    open_items: list[str]
    user_doubts: list[str]


@dataclasses.dataclass(frozen=True)
class Turn:
    user: str
    reply: str


def retry_prompt(missing: list[str]) -> str:
    return (
        f"The summary is incomplete or not valid JSON. Missing or invalid: {', '.join(missing)}. "
        "Reply again with only the complete JSON object."
    )


def _json_object(text: str) -> dict | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = [fenced.group(1)] if fenced else []
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return None


def parse_summary(text: str) -> HandoffSummary:
    """Validate the agent's reply against the fixed template."""
    data = _json_object(text)
    if data is None:
        raise InvalidSummary(list(SUMMARY_FIELDS))
    missing: list[str] = []
    goal = data.get("goal")
    if not isinstance(goal, str) or not goal.strip():
        missing.append("goal")
    lists: dict[str, list[str]] = {}
    for field in SUMMARY_FIELDS[1:]:
        value = data.get(field)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            missing.append(field)
        else:
            lists[field] = [item.strip() for item in value if item.strip()]
    if missing:
        raise InvalidSummary(missing)
    return HandoffSummary(goal.strip(), lists["decisions"], lists["open_items"], lists["user_doubts"])


def last_turns(turns: list[Turn], count: int = VERBATIM_TURNS, cap: int = REPLY_CAP) -> list[Turn]:
    def capped(text: str) -> str:
        return text if len(text) <= cap else text[: cap - 1] + "…"

    return [Turn(t.user, capped(t.reply)) for t in turns[-count:]]


class SessionFacts:
    """What Socra saw happen, so the handoff never relies on the model's recall."""

    def __init__(self) -> None:
        self.files_touched: list[str] = []
        self.tools_used: Counter[str] = Counter()
        self.permissions: list[tuple[str, str, bool]] = []
        self.exam_results: list[tuple[str, str, str]] = []

    def record_tool(self, activity: ToolActivity) -> None:
        self.tools_used[activity.tool] += 1
        if activity.tool in FILE_TOOLS and activity.path and activity.path not in self.files_touched:
            self.files_touched.append(activity.path)

    def record_permission(self, tool: str, title: str, allowed: bool) -> None:
        self.permissions.append((tool, title, allowed))

    def record_exam_result(self, question: str, verdict: str, note: str) -> None:
        self.exam_results.append((question, verdict, note))


def _bullets(items: list[str], empty: str = "none") -> str:
    return "\n".join(f"- {item}" for item in items) if items else f"- {empty}"


def render_seed(
    mode: Mode, facts: SessionFacts, summary: HandoffSummary, turns: list[Turn]
) -> str:
    """The hidden first message of the new session."""
    tools = [f"{tool}: {count}" for tool, count in facts.tools_used.items()]
    permissions = [
        f"{tool}: {title} ({'allowed' if allowed else 'denied'})"
        for tool, title, allowed in facts.permissions
    ]
    results = [
        f"{question}: {verdict}" + (f" ({note})" if note else "")
        for question, verdict, note in facts.exam_results
    ]
    conversation = "\n".join(f"User: {t.user}\nAgent: {t.reply}" for t in turns) or "none"
    return (
        f"You are continuing earlier work in {mode.label.lower()} mode. The previous session "
        "was closed; this is what Socra carries over.\n\n"
        f"## Recorded by Socra\nFiles changed:\n{_bullets(facts.files_touched)}\n"
        f"Tools used:\n{_bullets(tools)}\nPermission decisions:\n{_bullets(permissions)}\n"
        f"Exam results:\n{_bullets(results)}\n\n"
        f"## Summary written by the previous agent\nGoal: {summary.goal}\n"
        f"Decisions:\n{_bullets(summary.decisions)}\nOpen items:\n{_bullets(summary.open_items)}\n"
        f"User doubts:\n{_bullets(summary.user_doubts)}\n\n"
        f"## Last turns, verbatim\n{conversation}\n\n"
        "If something is missing, call search_transcript to look it up in the previous "
        "session. Now say, in one spoken sentence, what you understand the situation to be, "
        "so the user can correct you. Do not start any work yet."
    )
