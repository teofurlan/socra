"""One-line description of a tool call, shared by the agent adapters."""
from __future__ import annotations

from typing import Any

# Input keys that best describe a tool call in one line, in order of preference.
_SUMMARY_KEYS = ("description", "command", "file_path", "path", "pattern", "url", "query")
_SUMMARY_MAX = 120


def summarize_tool_input(tool_input: dict[str, Any]) -> str:
    for key in _SUMMARY_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            return text if len(text) <= _SUMMARY_MAX else text[: _SUMMARY_MAX - 1] + "…"
    return ""


def tool_path(tool_input: dict[str, Any]) -> str:
    """The file a tool call acts on, or an empty string when it names none."""
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""
