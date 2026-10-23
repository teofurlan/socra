"""Pure walkthrough rules: input validation, spoken commands, step cursor."""
from __future__ import annotations

import pytest

from socra_server.domain.walkthrough import (
    StepCursor,
    parse_command,
    parse_walkthrough,
)

CODE = "a = 1\nb = 2\nc = a + b\nprint(c)"


def steps(*pairs):
    return [{"say": say, "focus": {"lines": list(lines)}} for say, lines in pairs]


def test_valid_walkthrough_is_parsed_with_one_based_inclusive_lines():
    walkthrough, errors = parse_walkthrough(CODE, "python", steps(("Two names.", (1, 2)), ("Add.", (3, 3))))
    assert errors == []
    assert walkthrough is not None
    assert walkthrough.code == CODE
    assert walkthrough.language == "python"
    assert [(s.say, s.lines) for s in walkthrough.steps] == [("Two names.", (1, 2)), ("Add.", (3, 3))]


def test_focus_is_optional_and_means_nothing_highlighted():
    walkthrough, errors = parse_walkthrough(CODE, "", [{"say": "Overview."}])
    assert errors == []
    assert walkthrough is not None and walkthrough.steps[0].lines is None


def test_a_trailing_newline_does_not_add_a_line():
    walkthrough, errors = parse_walkthrough("a\nb\n", "", steps(("Both.", (1, 2))))
    assert errors == [] and walkthrough is not None


@pytest.mark.parametrize(
    "lines, fragment",
    [
        ((0, 2), "start at 1"),
        ((3, 2), "before its start"),
        ((1, 99), "only has 4 lines"),
        ((5, 6), "only has 4 lines"),
    ],
)
def test_out_of_range_lines_are_reported_per_step(lines, fragment):
    walkthrough, errors = parse_walkthrough(CODE, "python", steps(("Fine.", (1, 1)), ("Bad.", lines)))
    assert walkthrough is None
    assert len(errors) == 1
    assert errors[0]["step"] == 2
    assert errors[0]["field"] == "focus.lines"
    assert fragment in errors[0]["message"]


def test_every_problem_is_reported_not_only_the_first():
    bad = [
        {"say": "", "focus": {"lines": [1, 1]}},
        {"say": "ok", "focus": {"lines": "1-2"}},
        {"say": "ok", "focus": {"lines": [1.5, 2]}},
        {"say": "ok", "focus": {"lines": [True, 2]}},
        {"say": 3},
        "not a step",
    ]
    walkthrough, errors = parse_walkthrough(CODE, "", bad)
    assert walkthrough is None
    assert [(e["step"], e["field"]) for e in errors] == [
        (1, "say"), (2, "focus.lines"), (3, "focus.lines"), (4, "focus.lines"), (5, "say"), (6, "step"),
    ]


def test_empty_code_and_empty_steps_are_rejected():
    _, errors = parse_walkthrough("  \n", "", [])
    assert {(e["step"], e["field"]) for e in errors} == {(None, "code"), (None, "steps")}


@pytest.mark.parametrize(
    "text, command",
    [
        ("Repeat.", "repeat"),
        ("say that again", "repeat"),
        ("otra vez", "repeat"),
        ("Go back!", "back"),
        ("previous step", "back"),
        ("atrás", "back"),
        ("next", "next"),
        ("skip", "next"),
        ("siguiente", "next"),
        ("continue", "resume"),
        ("keep going", "resume"),
        ("continúa", "resume"),
        ("stop", "stop"),
        ("that's enough", "stop"),
        ("para", "stop"),
        ("hold on", "pause"),
        ("espera", "pause"),
    ],
)
def test_spoken_commands_are_recognised(text, command):
    assert parse_command(text) == command


@pytest.mark.parametrize("text", ["", "what does the loop do", "I think it adds two numbers", "backend"])
def test_other_speech_is_not_a_command(text):
    assert parse_command(text) is None


def test_cursor_moves_between_steps_and_clamps_at_the_start():
    cursor = StepCursor(total=3)
    assert cursor.index == 0
    assert cursor.apply("back") == "play" and cursor.index == 0
    assert cursor.apply("next") == "play" and cursor.index == 1
    assert cursor.apply("repeat") == "play" and cursor.index == 1
    assert cursor.apply("resume") == "play" and cursor.index == 1
    assert cursor.apply("back") == "play" and cursor.index == 0


def test_cursor_finishes_after_the_last_step_and_on_stop():
    cursor = StepCursor(total=2)
    cursor.apply("next")
    assert cursor.apply("next") == "finished"
    assert StepCursor(total=2).apply("stop") == "stopped"
    assert cursor.advance() == "finished"
    fresh = StepCursor(total=2)
    assert fresh.advance() == "play" and fresh.index == 1
