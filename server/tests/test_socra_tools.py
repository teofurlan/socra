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

    async def clear_scene(self) -> str:
        self.calls.append(("clear",))
        return "cleared"

    async def point_at(self, targets) -> str:
        self.calls.append(("point", targets))
        return "pointed"

    async def show_result(self, args) -> str:
        self.calls.append(("show", args))
        return "shown"

    async def replay_step(self, args) -> str:
        self.calls.append(("replay", args))
        return "replayed"


def _spec(name):
    return next(s for s in TOOL_SPECS if s.id == name)


def test_specs_for_a_mode_are_exactly_the_tools_it_lists():
    assert [s.id for s in specs_for(get_mode("mentor"))] == [
        "switch_mode", "search_transcript", "record_exam_result", "scene_guide", "present", "clear_scene",
        "point_at", "show_result", "replay_step",
    ]
    assert {s.id for s in specs_for(get_mode("exam"))} == {
        "switch_mode", "search_transcript", "record_exam_result", "scene_guide", "present", "clear_scene",
        "point_at", "show_result", "replay_step",
    }


async def test_clear_scene_takes_no_arguments_and_calls_the_toolbox():  # S4
    toolbox = RecordingToolbox()

    spec = _spec("clear_scene")

    assert spec.schema == {"type": "object", "properties": {}}
    assert "removes" in spec.description.lower() and "screen" in spec.description
    assert await spec.handler(toolbox, {}) == "cleared"
    assert toolbox.calls == [("clear",)]


def test_record_exam_result_covers_exam_and_check_answers():  # S3
    assert "check" in _spec("record_exam_result").description


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

    async def play(scene):
        return ""

    async def clear():
        seen.append("clear")
        return "ok"

    async def point(targets):
        seen.append(("point", targets))
        return "ok"

    async def show(args):
        seen.append(("show", args))
        return "ok"

    async def replay(step):
        seen.append(("replay", step))
        return "ok"

    toolbox = CallbackToolbox(
        switch=switch, record=record, search=search, play=play, clear=clear, point=point, show=show, replay=replay,
    )

    await toolbox.switch_mode("mentor")
    await toolbox.record_exam_result("Q", "correct", "")
    await toolbox.search_transcript("q", 2)
    await toolbox.clear_scene()
    await toolbox.point_at([])
    await toolbox.show_result({"object": "t"})
    await toolbox.replay_step("s")

    assert seen == [
        "mentor", ("Q", "correct", ""), ("q", 2), "clear", ("point", []), ("show", {"object": "t"}), ("replay", "s"),
    ]


async def test_point_at_passes_the_targets_to_the_toolbox():  # S5
    toolbox = RecordingToolbox()
    spec = _spec("point_at")

    assert await spec.handler(toolbox, {"targets": [{"object": "src", "lines": [1, 2]}]}) == "pointed"
    assert await spec.handler(toolbox, {}) == "pointed"
    assert toolbox.calls == [("point", [{"object": "src", "lines": [1, 2]}]), ("point", None)]


def test_point_at_schema_and_description_teach_targets_and_part_ids():  # S5, S6, S10
    spec = _spec("point_at")
    target = spec.schema["properties"]["targets"]["items"]["properties"]

    assert spec.schema["type"] == "object" and "targets" in spec.schema["properties"]
    assert set(target) == {"object", "part", "lines"}
    assert target["lines"]["minItems"] == 2 and target["lines"]["maxItems"] == 2
    for word in ("right before", "cell:", "bucket:", "entry:", "node:", "lines", "empty"):
        assert word in spec.description, word


async def test_show_result_passes_object_and_op_to_the_toolbox():  # S7
    toolbox = RecordingToolbox()
    spec = _spec("show_result")
    op = {"action": "insert", "params": {"key": 7}}

    assert await spec.handler(toolbox, {"object": "ht", "op": op}) == "shown"
    assert toolbox.calls == [("show", {"object": "ht", "op": op})]


def test_show_result_schema_and_description_teach_the_prediction_flow():  # S7, S10
    spec = _spec("show_result")

    assert spec.schema["required"] == ["object", "op"]
    assert set(spec.schema["properties"]) == {"object", "op"}
    for word in ("prediction", "answer", "insert", "outcome"):
        assert word in spec.description, word


async def test_replay_step_passes_its_arguments_to_the_toolbox():  # S8, S11
    toolbox = RecordingToolbox()
    spec = _spec("replay_step")
    args = {"step": "sum", "say": "New words.", "targets": [{"object": "src"}]}

    assert await spec.handler(toolbox, args) == "replayed"
    assert toolbox.calls == [("replay", args)]


def test_replay_step_schema_and_description_teach_when_to_replay():  # S8, S10
    spec = _spec("replay_step")

    assert spec.schema["required"] == ["step", "say"]
    assert set(spec.schema["properties"]) == {"step", "say", "targets"}
    for word in ("accepts", "step", "again", "NEW", "original", "targets"):
        assert word in spec.description, word
