"""Tests for the mode definitions."""
from __future__ import annotations

import pytest

from socra_server.domain.modes import DEFAULT_MODE, MODES, UnknownMode, get_mode


def test_two_modes_with_mentor_as_the_default():
    assert list(MODES) == ["mentor", "exam"]
    assert DEFAULT_MODE == "mentor"
    with pytest.raises(UnknownMode):
        get_mode("agent")


def test_the_switch_mode_tool_offers_only_mentor_and_exam():
    from socra_server.socra_tools import TOOL_SPECS

    spec = next(s for s in TOOL_SPECS if s.id == "switch_mode")
    assert spec.schema["properties"]["mode"]["enum"] == ["mentor", "exam"]
    assert "coding" not in spec.description


def test_every_mode_can_switch_and_search_the_previous_session():
    for mode in MODES.values():
        assert {"switch_mode", "search_transcript"} <= mode.tools


def test_every_mode_replies_in_the_language_socra_listens_and_speaks():
    from socra_server.domain.speech import SPEECH_LANGUAGE, SPEECH_LANGUAGE_NAME

    assert SPEECH_LANGUAGE == "en"
    for mode in MODES.values():
        assert f"Always reply in {SPEECH_LANGUAGE_NAME}" in mode.instructions


def test_mode_instructions_tell_the_agent_to_reply_in_english():  # S5
    for mode in MODES.values():
        assert "Always reply in English" in mode.instructions
        assert "Spanish" not in mode.instructions


def test_only_exam_records_exam_results():
    assert "record_exam_result" in get_mode("exam").tools
    assert "record_exam_result" not in get_mode("mentor").tools


def test_mentor_placeholder_is_a_read_only_explainer():
    instructions = get_mode("mentor").instructions.lower()
    assert "explain" in instructions
    assert "do not edit" in instructions


def test_unknown_mode_is_rejected():
    with pytest.raises(UnknownMode):
        get_mode("poet")


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
def test_both_modes_offer_scene_guide_alongside_present(mode_id):  # S1
    tools = get_mode(mode_id).tools
    assert "scene_guide" in tools
    assert "present" in tools
