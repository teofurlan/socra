"""Mode switching in AgentApp: handoff, confirmation, failures and Pi blocking."""
from __future__ import annotations

import asyncio
import json

from socra_server.adapters.transcript_store import TranscriptStore
from socra_server.agent_app import AgentApp
from socra_server.agent_registry import BackendRegistry
from socra_server.domain.agent import (
    AgentError,
    BackendStatus,
    ModelOption,
    PermissionRequest,
    ReplyDone,
    ToolActivity,
)
from socra_server.domain.handoff import SUMMARY_PROMPT
from tests.test_agent_app import FakeChannel, FakeLoader, _finish_turn

VALID = json.dumps({
    "goal": "Add login", "decisions": ["Use Auth0"], "open_items": ["Tests"], "user_doubts": [],
})


class Convo:
    """Answers each send with the next scripted list of events."""

    def __init__(self, scripts, decide=None, gate: asyncio.Event | None = None) -> None:
        self.scripts = list(scripts)
        self.decide = decide
        self.gate = gate
        self.turns: list[str] = []
        self.closed = False
        self.interrupted = False

    async def send(self, text):
        self.turns.append(text)
        if self.gate is not None:
            await self.gate.wait()
        script = self.scripts.pop(0) if self.scripts else [ReplyDone("ok")]
        for item in script:
            if isinstance(item, PermissionRequest):
                await self.decide(item)
            else:
                yield item

    async def interrupt(self):
        self.interrupted = True

    async def close(self):
        self.closed = True


class ModeBackend:
    id = "fake"
    label = "Fake"

    def __init__(self, conversations, supports_modes=True, fail_after: int | None = None):
        self.supports_modes = supports_modes
        self.queue = list(conversations)
        self.fail_after = fail_after
        self.opens: list[dict] = []

    def models(self):
        return [ModelOption("small", "Small")]

    async def check(self):
        return BackendStatus("ready")

    async def open(self, model, cwd, decide_permission, **kwargs):
        if self.fail_after is not None and len(self.opens) >= self.fail_after:
            raise RuntimeError("CLI crashed")
        self.opens.append(kwargs)
        convo = self.queue.pop(0)
        convo.decide = decide_permission
        return convo


class PlainBackend(ModeBackend):
    """A backend without modes: open takes no mode or toolbox."""

    def __init__(self, conversations):
        super().__init__(conversations, supports_modes=False)

    async def open(self, model, cwd, decide_permission):
        return self.queue.pop(0)


def _make(backend, tmp_path, store=True):
    channel = FakeChannel()
    loader = FakeLoader()
    app = AgentApp(
        channel=channel,
        registry=BackendRegistry([backend]),
        loader=loader,
        folder_picker=lambda: None,
        transcripts=TranscriptStore(tmp_path / "sessions") if store else None,
    )
    return app, channel, loader


async def _started(app, tmp_path):
    await app.handle_start("fake", "small", str(tmp_path))
    for _ in range(50):
        if app._conversation is not None:
            return
        await asyncio.sleep(0)
    raise AssertionError("conversation never opened")


async def _switch(app, channel, target):
    await app.handle_switch_mode(target)
    assert app.switch_task is not None
    await asyncio.wait_for(app.switch_task, timeout=3)
    if app.turn_task is not None:
        await _finish_turn(app, channel)


def _texts(channel, kind):
    return [m for m in channel.sent if m["type"] == kind]


async def test_start_opens_with_the_agent_mode_and_a_toolbox(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)

    await _started(app, tmp_path)

    assert backend.opens[0]["mode"].id == "agent"
    assert backend.opens[0]["toolbox"] is not None
    await app.handle_hello()
    assert channel.of_type("agent_backends")[-1]["session"]["mode"] == "agent"


async def test_a_backend_without_modes_is_opened_the_plain_way(tmp_path):
    app, channel, _ = _make(PlainBackend([Convo([])]), tmp_path)

    await _started(app, tmp_path)

    assert app._conversation is not None


async def test_starting_in_another_mode_on_a_backend_without_modes_is_rejected(tmp_path):
    app, channel, _ = _make(PlainBackend([Convo([])]), tmp_path)

    await app.handle_start("fake", "small", str(tmp_path), mode="exam")

    assert "Claude Code" in channel.of_type("agent_error")[-1]["message"]
    assert not channel.of_type("agent_started")


async def test_switching_on_a_backend_without_modes_is_rejected_with_an_error(tmp_path):
    app, channel, _ = _make(PlainBackend([Convo([])]), tmp_path)
    await _started(app, tmp_path)

    await app.handle_switch_mode("exam")

    assert app.switch_task is None
    assert channel.of_type("agent_error")[-1]["message"] == "Mode switching needs Claude Code."


async def test_selector_switch_hands_off_to_a_new_session_and_restates(tmp_path):
    old = Convo([[ReplyDone("Login added.")], [ReplyDone(VALID)]])
    new = Convo([[ReplyDone("We built login; shall I quiz you?")]])
    backend = ModeBackend([old, new])
    app, channel, loader = _make(backend, tmp_path)
    await _started(app, tmp_path)
    await app.handle_turn_text("add a login page")
    await _finish_turn(app, channel)
    before = len(channel.sent)
    loader.tts.spoken.clear()

    await _switch(app, channel, "exam")
    sent = channel.sent[before:]

    assert old.turns[1] == SUMMARY_PROMPT
    assert old.closed
    assert backend.opens[1]["mode"].id == "exam"
    seed = new.turns[0]
    assert "Add login" in seed and "Use Auth0" in seed
    assert "add a login page" in seed and "Login added." in seed
    kinds = [m["type"] for m in sent]
    assert kinds.index("agent_switching") < kinds.index("agent_mode_changed")
    assert [m for m in sent if m["type"] == "agent_mode_changed"][0] == {
        "type": "agent_mode_changed", "mode": "exam", "backend": "fake", "model": "small",
        "cwd": str(tmp_path),
    }
    # The summary turn is silent: only the restatement reaches the page and the speaker.
    assert [m["text"] for m in sent if m["type"] == "agent_reply"] == [
        "We built login; shall I quiz you?"
    ]
    assert loader.tts.spoken == ["We built login; shall I quiz you?"]
    # The hidden seed is not shown as a user turn.
    assert not [m for m in sent if m["type"] == "transcript"]
    await app.handle_hello()
    assert channel.of_type("agent_backends")[-1]["session"]["mode"] == "exam"


async def test_the_handoff_carries_what_socra_recorded_itself(tmp_path):
    old = Convo([
        [ToolActivity("Edit", "a.py", "src/a.py"),
         PermissionRequest("p1", "Bash", "Run tests"),
         ReplyDone("Edited.")],
        [ReplyDone(VALID)],
    ])
    new = Convo([[ReplyDone("ok")]])
    app, channel, _ = _make(ModeBackend([old, new]), tmp_path)
    await _started(app, tmp_path)
    await app.handle_turn_text("edit it")
    for _ in range(100):
        if channel.of_type("permission_request"):
            break
        await asyncio.sleep(0)
    await app.handle_permission_response("p1", False)
    await _finish_turn(app, channel)

    await _switch(app, channel, "mentor")

    seed = new.turns[0]
    assert "src/a.py" in seed
    assert "Bash: Run tests (denied)" in seed


async def test_exam_results_recorded_through_the_tool_reach_the_next_handoff(tmp_path):
    first = Convo([[ReplyDone("Q1?")], [ReplyDone(VALID)]])
    second = Convo([[ReplyDone("ok")]])
    backend = ModeBackend([first, second])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]

    await toolbox.record_exam_result("What is a port?", "partial", "missed adapters")
    await _switch(app, channel, "mentor")

    assert "What is a port?: partial (missed adapters)" in second.turns[0]


async def test_the_new_session_can_search_the_previous_transcript(tmp_path):
    first = Convo([[ReplyDone("We chose Auth0 for tokens.")], [ReplyDone(VALID)]])
    second = Convo([[ReplyDone("ok")]])
    backend = ModeBackend([first, second])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]
    await app.handle_turn_text("which provider?")
    await _finish_turn(app, channel)
    # The first session has no previous transcript to search.
    assert await toolbox.search_transcript("auth0", 5) == []
    await _switch(app, channel, "mentor")

    hits = await toolbox.search_transcript("auth0", 5)

    assert [(h.role, "Auth0" in h.snippet) for h in hits] == [("agent", True)]


async def test_an_incomplete_summary_is_requested_again(tmp_path):
    incomplete = json.dumps({"goal": "Add login", "decisions": []})
    old = Convo([[ReplyDone(incomplete)], [ReplyDone(VALID)]])
    new = Convo([[ReplyDone("ok")]])
    app, channel, _ = _make(ModeBackend([old, new]), tmp_path)
    await _started(app, tmp_path)

    await _switch(app, channel, "exam")

    assert len(old.turns) == 2
    assert "open_items, user_doubts" in old.turns[1]
    assert _texts(channel, "agent_mode_changed")


async def test_three_invalid_summaries_abort_and_keep_the_old_mode(tmp_path):
    old = Convo([[ReplyDone("no json")]] * 3)
    backend = ModeBackend([old, Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await _switch(app, channel, "exam")

    assert len(old.turns) == 3
    assert not old.closed
    assert len(backend.opens) == 1
    assert "summary" in channel.of_type("agent_error")[-1]["message"]
    assert _texts(channel, "mode_switch_failed") == [{"type": "mode_switch_failed", "mode": "agent"}]
    await app.handle_hello()
    assert channel.of_type("agent_backends")[-1]["session"]["mode"] == "agent"


async def test_a_new_session_that_fails_to_start_leaves_the_old_one_working(tmp_path):
    old = Convo([[ReplyDone(VALID)], [ReplyDone("still here")]])
    backend = ModeBackend([old], fail_after=1)
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await _switch(app, channel, "exam")

    assert not old.closed
    assert "CLI crashed" in channel.of_type("agent_error")[-1]["message"]
    assert _texts(channel, "mode_switch_failed")
    await app.handle_turn_text("hello?")
    await _finish_turn(app, channel)
    assert old.turns[-1] == "hello?"


async def test_a_summary_turn_error_counts_as_a_failed_attempt(tmp_path):
    old = Convo([[AgentError("boom")], [ReplyDone(VALID)]])
    new = Convo([[ReplyDone("ok")]])
    app, channel, _ = _make(ModeBackend([old, new]), tmp_path)
    await _started(app, tmp_path)

    await _switch(app, channel, "mentor")

    assert _texts(channel, "agent_mode_changed")
    assert not channel.of_type("agent_error")


async def test_same_or_unknown_modes_are_not_switched(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await app.handle_switch_mode("agent")
    await app.handle_switch_mode("poet")

    assert app.switch_task is None
    assert channel.of_type("notice")[-1]["text"] == "Already in Agent mode."
    assert "Unknown mode" in channel.of_type("agent_error")[-1]["message"]


async def test_a_voice_request_waits_for_the_confirmation_on_screen(tmp_path):
    old = Convo([[ReplyDone(VALID)]])
    new = Convo([[ReplyDone("ok")]])
    backend = ModeBackend([old, new])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]

    answer = await toolbox.switch_mode("exam")

    assert "asked the user" in answer.lower()
    assert channel.of_type("mode_switch_request") == [
        {"type": "mode_switch_request", "mode": "exam", "label": "Exam"}
    ]
    assert app.switch_task is None
    assert len(backend.opens) == 1

    await app.handle_mode_switch_response("exam", True)
    await asyncio.wait_for(app.switch_task, timeout=3)

    assert backend.opens[1]["mode"].id == "exam"


async def test_declining_a_voice_request_changes_nothing(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await backend.opens[0]["toolbox"].switch_mode("exam")
    await app.handle_mode_switch_response("exam", False)

    assert app.switch_task is None
    assert channel.of_type("mode_switch_closed") == [{"type": "mode_switch_closed", "mode": "exam"}]


async def test_a_response_nobody_asked_for_is_ignored(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await app.handle_mode_switch_response("exam", True)

    assert app.switch_task is None


async def test_the_tool_refuses_the_current_or_an_unknown_mode(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]

    assert "Already" in await toolbox.switch_mode("agent")
    assert "Unknown" in await toolbox.switch_mode("poet")
    assert not channel.of_type("mode_switch_request")


async def test_turns_wait_while_a_switch_is_running(tmp_path):
    gate = asyncio.Event()
    old = Convo([[ReplyDone(VALID)]], gate=gate)
    backend = ModeBackend([old, Convo([[ReplyDone("ok")]])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await app.handle_switch_mode("exam")
    await asyncio.sleep(0)
    await app.handle_turn_text("hi")

    assert channel.of_type("notice")[-1]["text"] == "Wait for the mode switch to finish."
    gate.set()
    await asyncio.wait_for(app.switch_task, timeout=3)


async def test_interrupt_cancels_a_running_switch(tmp_path):
    gate = asyncio.Event()
    old = Convo([[ReplyDone(VALID)]], gate=gate)
    backend = ModeBackend([old, Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)

    await app.handle_switch_mode("exam")
    await asyncio.sleep(0)
    await app.handle_interrupt()

    assert app.switch_task is None or app.switch_task.done()
    assert old.interrupted
    assert _texts(channel, "mode_switch_failed")
    assert len(backend.opens) == 1
    assert not old.closed


async def test_a_voice_switch_waits_for_the_running_reply_to_finish(tmp_path):
    gate = asyncio.Event()
    old = Convo([[ReplyDone("working...")], [ReplyDone(VALID)]], gate=gate)
    backend = ModeBackend([old, Convo([[ReplyDone("ok")]])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    await app.handle_turn_text("do it")
    await asyncio.sleep(0)
    await backend.opens[0]["toolbox"].switch_mode("mentor")

    await app.handle_mode_switch_response("mentor", True)
    await asyncio.sleep(0.01)
    assert old.turns == ["do it"]  # the summary is not requested mid-reply
    gate.set()
    await _finish_turn(app, channel)
    await asyncio.wait_for(app.switch_task, timeout=3)

    assert old.turns[1] == SUMMARY_PROMPT


async def test_without_a_transcript_store_the_switch_still_works(tmp_path):
    old = Convo([[ReplyDone(VALID)]])
    backend = ModeBackend([old, Convo([[ReplyDone("ok")]])])
    app, channel, _ = _make(backend, tmp_path, store=False)
    await _started(app, tmp_path)

    await _switch(app, channel, "exam")

    assert backend.opens[1]["mode"].id == "exam"
    assert await backend.opens[1]["toolbox"].search_transcript("x", 5) == []
