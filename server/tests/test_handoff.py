"""Tests for the handoff: summary validation, recorded facts, verbatim turns and the seed."""
from __future__ import annotations

import json

import pytest

from socra_server.domain.agent import ToolActivity
from socra_server.domain.handoff import (
    InvalidSummary,
    SessionFacts,
    Turn,
    HandoffSummary,
    last_turns,
    parse_summary,
    render_seed,
    retry_prompt,
)
from socra_server.domain.modes import get_mode

VALID = {
    "goal": "Add login",
    "decisions": ["Use Auth0"],
    "open_items": ["Write tests"],
    "user_doubts": [],
}


def test_tool_activity_path_defaults_to_empty():
    assert ToolActivity("Read", "x").path == ""


def test_parse_accepts_plain_json_and_fenced_json():
    plain = parse_summary(json.dumps(VALID))
    fenced = parse_summary("Here you go:\n```json\n" + json.dumps(VALID) + "\n```")

    assert plain == fenced == HandoffSummary("Add login", ["Use Auth0"], ["Write tests"], [])


def test_parse_reports_every_missing_field():
    with pytest.raises(InvalidSummary) as error:
        parse_summary(json.dumps({"goal": "  ", "decisions": ["a"], "open_items": None}))

    assert error.value.missing == ["goal", "open_items", "user_doubts"]


def test_parse_rejects_text_without_json():
    with pytest.raises(InvalidSummary) as error:
        parse_summary("I could not summarise that.")

    assert error.value.missing == ["goal", "decisions", "open_items", "user_doubts"]


def test_parse_drops_blank_items_and_rejects_non_string_lists():
    summary = parse_summary(json.dumps({**VALID, "decisions": ["a", " ", "b"]}))
    assert summary.decisions == ["a", "b"]
    with pytest.raises(InvalidSummary) as error:
        parse_summary(json.dumps({**VALID, "decisions": [1, 2]}))
    assert error.value.missing == ["decisions"]


def test_retry_prompt_names_the_missing_fields():
    assert "goal, open_items" in retry_prompt(["goal", "open_items"])


def test_last_turns_keeps_four_pairs_and_caps_replies():
    turns = [Turn(f"q{i}", "r" * 2000 if i == 5 else f"a{i}") for i in range(6)]

    kept = last_turns(turns)

    assert [t.user for t in kept] == ["q2", "q3", "q4", "q5"]
    assert len(kept[-1].reply) <= 1500
    assert kept[-1].reply.endswith("…")
    assert kept[0].reply == "a2"


def test_facts_record_files_only_for_file_changing_tools():
    facts = SessionFacts()
    facts.record_tool(ToolActivity("Edit", "a.py", "src/a.py"))
    facts.record_tool(ToolActivity("Edit", "a.py", "src/a.py"))
    facts.record_tool(ToolActivity("Write", "b.py", "src/b.py"))
    facts.record_tool(ToolActivity("Read", "c.py", "src/c.py"))
    facts.record_tool(ToolActivity("Bash", "ls"))

    assert facts.files_touched == ["src/a.py", "src/b.py"]
    assert facts.tools_used == {"Edit": 2, "Write": 1, "Read": 1, "Bash": 1}


def test_facts_record_permissions_and_exam_results():
    facts = SessionFacts()
    facts.record_permission("Bash", "Run tests", True)
    facts.record_permission("Bash", "rm -rf", False)
    facts.record_exam_result("What is a port?", "partial", "missed the adapter side")

    assert facts.permissions == [("Bash", "Run tests", True), ("Bash", "rm -rf", False)]
    assert facts.exam_results == [("What is a port?", "partial", "missed the adapter side")]


def test_seed_carries_facts_summary_turns_and_the_restatement_request():  # also pins S3
    facts = SessionFacts()
    facts.record_tool(ToolActivity("Edit", "a.py", "src/a.py"))
    facts.record_permission("Bash", "Run tests", False)
    facts.record_exam_result("Q1", "correct", "")
    summary = HandoffSummary("Add login", ["Use Auth0"], ["Write tests"], ["Is the token stored?"])

    seed = render_seed(get_mode("mentor"), facts, summary, [Turn("hi", "hello")])

    for expected in ("mentor", "src/a.py", "Edit: 1", "Bash: Run tests (denied)", "Q1: correct",
                     "Add login", "Use Auth0", "Write tests", "Is the token stored?",
                     "hi", "hello", "search_transcript"):
        assert expected in seed
    assert "Now say, in one spoken sentence, what you understand the situation to be" in seed
    assert "Do not start any work yet." in seed


def test_seed_asks_to_answer_what_the_user_said_during_the_switch():
    summary = HandoffSummary("Add login", [], [], [])

    seed = render_seed(get_mode("mentor"), SessionFacts(), summary, [], ["fix the login first"])

    assert "fix the login first" in seed
    assert "Answer what the user said during the switch directly" in seed
    assert "one spoken sentence" not in seed


@pytest.mark.parametrize("mode_id", ["mentor", "exam"])
@pytest.mark.parametrize("pending", [None, ["fix the login first"]])
def test_seed_states_the_switch_is_confirmed_and_done(mode_id, pending):  # S1
    summary = HandoffSummary("Add login", [], [], [])

    seed = render_seed(get_mode(mode_id), SessionFacts(), summary, [], pending)

    assert "already confirmed the switch" in seed
    assert f"The switch is complete and the session is now in {mode_id} mode" in seed
    assert "Do not ask the user to confirm, accept or press anything about the switch" in seed


def test_exam_seed_tells_the_agent_to_start_the_exam_now():  # S2
    summary = HandoffSummary("Add login", [], [], [])

    seed = render_seed(get_mode("exam"), SessionFacts(), summary, [])

    assert "Start the exam now" in seed
    assert "first question right away" in seed
    assert "Do not restate the situation" in seed
    assert "Do not start any work yet" not in seed
    assert "one spoken sentence" not in seed


def test_mentor_seed_keeps_the_restatement_closing():  # S3
    summary = HandoffSummary("Add login", [], [], [])

    seed = render_seed(get_mode("mentor"), SessionFacts(), summary, [])

    assert (
        "Now say, in one spoken sentence, what you understand the situation to be, "
        "so the user can correct you. Do not start any work yet."
    ) in seed
    assert "Start the exam now" not in seed


def test_exam_seed_with_pending_words_answers_them_then_continues_the_exam():  # S4
    summary = HandoffSummary("Add login", [], [], [])

    seed = render_seed(get_mode("exam"), SessionFacts(), summary, [], ["fix the login first"])

    assert "fix the login first" in seed
    assert "Answer what the user said during the switch directly" in seed
    assert "Then continue the exam" in seed
    assert "ask the first question if you have not asked it yet" in seed
    mentor = render_seed(get_mode("mentor"), SessionFacts(), summary, [], ["x"])
    assert "Then continue the exam" not in mentor
