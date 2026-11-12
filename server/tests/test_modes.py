"""Tests for the mode definitions."""
from __future__ import annotations

import pytest

from socra_server.domain.modes import DEFAULT_MODE, MODES, UnknownMode, get_mode


def test_three_modes_with_mentor_as_the_default():  # S1
    assert list(MODES) == ["agent", "mentor", "exam"]
    assert DEFAULT_MODE == "mentor"
    with pytest.raises(UnknownMode):
        get_mode("poet")


def test_the_switch_mode_tool_offers_agent_mentor_and_exam():  # S3
    from socra_server.socra_tools import TOOL_SPECS

    spec = next(s for s in TOOL_SPECS if s.id == "switch_mode")
    assert spec.schema["properties"]["mode"]["enum"] == ["agent", "mentor", "exam"]
    assert "coding" in spec.description


def test_agent_is_a_coding_agent_that_speaks_briefly_and_keeps_the_voice_rules():  # S2
    mode = get_mode("agent")
    text = mode.instructions.lower()
    assert mode.label == "Agent"
    assert "coding agent" in text and "do not edit" not in text
    assert "never read code" in text
    assert "always reply in english" in text and "switch_mode" in mode.instructions
    assert mode.tools == {"switch_mode", "search_transcript"}


def test_agent_waits_for_the_go_ahead_after_a_handoff():  # S4
    opening = get_mode("agent").opening.lower()
    assert "one spoken sentence" in opening and "go-ahead" in opening


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


def test_mentor_and_exam_record_results_and_clear_the_scene():  # S3, S4
    for mode_id in ("mentor", "exam"):
        assert {"record_exam_result", "clear_scene"} <= get_mode(mode_id).tools


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
def test_instructions_describe_the_check_after_a_scene(mode_id):  # S1, S2, S3
    text = get_mode(mode_id).instructions.lower()
    assert "check" in text and "never" in text
    assert "record_exam_result" in text
    assert "clear_scene" in text


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


def test_mentor_and_exam_can_point_at_the_scene():  # S5
    for mode_id in ("mentor", "exam"):
        assert "point_at" in get_mode(mode_id).tools


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
def test_instructions_tell_the_agent_to_point_before_each_check_question(mode_id):  # S5, S10
    text = get_mode(mode_id).instructions
    assert "point_at" in text and "empty list" in text


def test_mentor_and_exam_can_show_results_and_replay_steps():  # S7, S8
    for mode_id in ("mentor", "exam"):
        assert {"show_result", "replay_step"} <= get_mode(mode_id).tools


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
def test_instructions_describe_the_prediction_question_and_the_replay(mode_id):  # S7, S8, S10
    text = get_mode(mode_id).instructions
    assert "show_result" in text and "prediction" in text and "replay_step" in text
    assert "incorrect or partial" in text


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
def test_instructions_ask_for_a_new_explanation_aimed_at_the_mistake_on_replay(mode_id):  # S11, S10
    text = get_mode(mode_id).instructions
    assert "new short explanation" in text and "never the step's original words" in text
    assert "targets" in text
