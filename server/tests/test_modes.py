"""Tests for the mode definitions."""
from __future__ import annotations

import pytest

from socra_server.domain.modes import DEFAULT_MODE, MODES, UnknownMode, get_mode


def test_three_modes_with_agent_as_the_default():
    assert list(MODES) == ["agent", "mentor", "exam"]
    assert DEFAULT_MODE == "agent"


def test_every_mode_can_switch_and_search_the_previous_session():
    for mode in MODES.values():
        assert {"switch_mode", "search_transcript"} <= mode.tools


def test_every_mode_replies_in_the_language_socra_listens_and_speaks():
    from socra_server.domain.speech import SPEECH_LANGUAGE, SPEECH_LANGUAGE_NAME

    assert SPEECH_LANGUAGE == "es"
    for mode in MODES.values():
        assert f"Always reply in {SPEECH_LANGUAGE_NAME}" in mode.instructions


def test_only_exam_records_exam_results():
    assert "record_exam_result" in get_mode("exam").tools
    assert "record_exam_result" not in get_mode("agent").tools
    assert "record_exam_result" not in get_mode("mentor").tools


def test_mentor_placeholder_is_a_read_only_explainer():
    instructions = get_mode("mentor").instructions.lower()
    assert "explain" in instructions
    assert "do not edit" in instructions


def test_unknown_mode_is_rejected():
    with pytest.raises(UnknownMode):
        get_mode("poet")
