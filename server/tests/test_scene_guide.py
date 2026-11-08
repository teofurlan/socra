"""The scene_guide skill: authoring rules, per-topic advice and valid example scenes (#70)."""
from __future__ import annotations

import json

import pytest

from socra_server.domain.modes import SCENE_GUIDE_TOOL, get_mode
from socra_server.domain.scene import PRESENT_SUMMARY, SCENE_GUIDE, parse_scene
from socra_server.domain.scene_guide import EXAMPLES, TOPICS, scene_guide
from socra_server.domain.speech import SPEECH_LANGUAGE_NAME
from socra_server.socra_tools import TOOL_SPECS, specs_for


class ExplodingToolbox:
    def __getattr__(self, name):
        raise AssertionError(f"scene_guide touched the toolbox: {name}")


def _example_of(text: str) -> dict:
    return json.loads(text.split("Example scene:")[1].strip())


def test_the_topics_are_code_and_concept():  # S3
    assert TOPICS == ("code", "concept")


@pytest.mark.parametrize("topic", TOPICS)
def test_every_topic_returns_the_authoring_rules(topic):  # S4, S5
    text = scene_guide(topic)
    assert "4 to 10 steps" in text
    assert "one idea per step" in text
    assert SPEECH_LANGUAGE_NAME in text
    assert "call present once more" in text
    assert "explain by voice" in text


@pytest.mark.parametrize("topic", TOPICS)
def test_every_topic_returns_the_format_reference(topic):  # S1
    assert SCENE_GUIDE in scene_guide(topic)


def test_code_topic_advice_is_about_reading_code_and_flows():  # S3
    text = scene_guide("code")
    assert "30 lines" in text
    assert "focus" in text
    assert "diagram" in text


def test_concept_topic_advice_is_about_structures():  # S3
    text = scene_guide("concept")
    assert "hash tables" in text
    assert "structure" in text
    assert "headline" in text


@pytest.mark.parametrize("topic", TOPICS)
def test_every_example_is_a_valid_scene(topic):  # S6
    example = _example_of(scene_guide(topic))
    scene, errors = parse_scene(example)
    assert errors == []
    assert scene is not None


@pytest.mark.parametrize("topic", TOPICS)
def test_every_example_has_4_to_10_steps(topic):  # S4, S6
    assert 4 <= len(EXAMPLES[topic]["steps"]) <= 10
    assert EXAMPLES[topic] == _example_of(scene_guide(topic))


def test_the_code_example_pairs_a_diagram_with_focused_code():  # S3, S6
    objects = EXAMPLES["code"]["objects"]
    assert {o["primitive"] for o in objects} >= {"diagram", "code"}
    actions = [a["action"] for cue in EXAMPLES["code"]["cues"] for a in cue["do"]]
    assert "focus" in actions


def test_the_concept_example_uses_a_hash_table_structure():  # S6, S8
    structures = [o for o in EXAMPLES["concept"]["objects"] if o["primitive"] == "structure"]
    assert [s["params"]["kind"] for s in structures] == ["hashTable"]
    headlines = [o for o in EXAMPLES["concept"]["objects"] if o["primitive"] == "headline"]
    assert len(headlines) <= 1


def test_an_unknown_topic_names_the_valid_ones():
    text = scene_guide("poem")
    assert "code" in text and "concept" in text
    assert '{"version"' not in text


def test_the_scene_guide_tool_returns_the_guide_without_the_toolbox():  # S1
    spec = next(s for s in TOOL_SPECS if s.id == SCENE_GUIDE_TOOL)
    assert spec.schema["properties"]["topic"]["enum"] == list(TOPICS)
    assert spec.schema["required"] == ["topic"]
    import asyncio

    text = asyncio.run(spec.handler(ExplodingToolbox(), {"topic": "concept"}))
    assert text == scene_guide("concept")


def test_both_modes_list_scene_guide():  # S1
    assert SCENE_GUIDE_TOOL == "scene_guide"
    for mode_id in ("mentor", "exam"):
        mode = get_mode(mode_id)
        assert SCENE_GUIDE_TOOL in mode.tools
        assert SCENE_GUIDE_TOOL in {s.id for s in specs_for(mode)}


def test_present_no_longer_embeds_the_whole_format_guide():  # S1, S5
    spec = next(s for s in TOOL_SPECS if s.id == "present")
    assert SCENE_GUIDE not in spec.description
    assert len(spec.description) < len(SCENE_GUIDE) / 2
    assert PRESENT_SUMMARY in spec.description
    assert "scene_guide" in spec.description
    assert "once more" in spec.description


def test_mentor_is_told_to_show_structure_flow_or_data():  # S2
    text = get_mode("mentor").instructions
    assert "scene_guide" in text and "present" in text
    assert "structure" in text and "flow" in text and "data" in text


def test_exam_may_show_the_code_a_question_refers_to_but_never_the_answer():  # S2
    text = get_mode("exam").instructions
    assert "scene_guide" in text
    assert "never show the answer" in text.lower()


async def test_the_mcp_server_exposes_scene_guide():  # S1, S10
    from socra_server.entrypoints.mcp_tools import create_mcp

    mcp = create_mcp()
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "scene_guide" in tools
    assert "scene_guide" in mcp.instructions
    assert SCENE_GUIDE not in tools["present"].description
    assert "scene_guide" in tools["present"].description
    assert "no_client" in tools["present"].description
    result = await mcp.call_tool("scene_guide", {"topic": "code"})
    assert "4 to 10 steps" in str(result)
