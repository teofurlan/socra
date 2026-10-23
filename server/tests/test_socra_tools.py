"""Tests for Socra's tool definitions, with a fake toolbox."""
from __future__ import annotations

from socra_server.adapters.transcript_store import TranscriptHit
from socra_server.domain.modes import get_mode
from socra_server.socra_tools import TOOL_SPECS, CallbackToolbox, specs_for


class RecordingToolbox:
    def __init__(self, hits=None):
        self.calls: list[tuple] = []
        self.hits = hits or []

    async def switch_mode(self, target: str) -> str:
        self.calls.append(("switch", target))
        return "asked"

    async def record_exam_result(self, question: str, verdict: str, note: str) -> str:
        self.calls.append(("record", question, verdict, note))
        return "recorded"

    async def search_transcript(self, query: str, limit: int):
        self.calls.append(("search", query, limit))
        return self.hits


def _spec(name):
    return next(s for s in TOOL_SPECS if s.id == name)


def test_specs_for_a_mode_are_exactly_the_tools_it_lists():
    assert [s.id for s in specs_for(get_mode("agent"))] == ["switch_mode", "search_transcript"]
    assert {s.id for s in specs_for(get_mode("exam"))} == {
        "switch_mode", "search_transcript", "record_exam_result",
    }


def test_every_spec_has_a_description_and_an_object_schema():
    for spec in TOOL_SPECS:
        assert spec.description
        assert spec.schema["type"] == "object"


async def test_switch_mode_passes_the_mode_to_the_toolbox():
    toolbox = RecordingToolbox()

    text = await _spec("switch_mode").handler(toolbox, {"mode": "exam"})

    assert toolbox.calls == [("switch", "exam")]
    assert text == "asked"


async def test_record_exam_result_validates_the_verdict_before_recording():
    toolbox = RecordingToolbox()

    bad = await _spec("record_exam_result").handler(
        toolbox, {"question": "Q", "verdict": "great"}
    )
    good = await _spec("record_exam_result").handler(
        toolbox, {"question": "Q", "verdict": "partial", "note": "n"}
    )

    assert "correct, partial or incorrect" in bad
    assert toolbox.calls == [("record", "Q", "partial", "n")]
    assert good == "recorded"


async def test_search_transcript_formats_hits_and_defaults_the_limit():
    toolbox = RecordingToolbox([TranscriptHit(3, "agent", "we chose Auth0")])

    text = await _spec("search_transcript").handler(toolbox, {"query": "auth"})

    assert toolbox.calls == [("search", "auth", 5)]
    assert "turn 3 (agent): we chose Auth0" in text


async def test_search_transcript_says_so_when_nothing_matches():
    text = await _spec("search_transcript").handler(RecordingToolbox(), {"query": "x"})

    assert "No matches" in text


async def test_callback_toolbox_delegates_to_its_callbacks():
    seen = []

    async def switch(target):
        seen.append(target)
        return "ok"

    async def record(question, verdict, note):
        seen.append((question, verdict, note))
        return "ok"

    async def search(query, limit):
        seen.append((query, limit))
        return []

    toolbox = CallbackToolbox(switch=switch, record=record, search=search)

    await toolbox.switch_mode("mentor")
    await toolbox.record_exam_result("Q", "correct", "")
    await toolbox.search_transcript("q", 2)

    assert seen == ["mentor", ("Q", "correct", ""), ("q", 2)]
