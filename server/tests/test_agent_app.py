"""Tests for the agent-mode application service, with fake backend, channel and speech."""
from __future__ import annotations

import asyncio
import base64
import io
import wave
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from socra_server.agent_app import AgentApp
from socra_server.agent_registry import BackendRegistry
from socra_server.domain.agent import (
    AgentError,
    AgentEvent,
    BackendStatus,
    ModelOption,
    PermissionRequest,
    ReplyDone,
    TextDelta,
    ToolActivity,
)


def _wav(seconds: float = 0.01) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buffer.getvalue()


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.is_connected = True

    async def send(self, message: dict) -> None:
        self.sent.append(message)

    def of_type(self, kind: str) -> list[dict]:
        return [m for m in self.sent if m["type"] == kind]


class FakeTTS:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return _wav()


class FakeSTT:
    def __init__(self, text: str) -> None:
        self.text = text

    def transcribe_with_glossary(self, wav_bytes: bytes, glossary) -> str:
        return self.text


class FakeLoader:
    def __init__(self, heard: str = "list the files") -> None:
        self.tts = FakeTTS()
        self.stt = FakeSTT(heard)

    async def ready(self) -> None:
        pass


class ScriptedConversation:
    """Replays events; a PermissionRequest in the script asks the decider."""

    def __init__(self, script, decide) -> None:
        self.script = script
        self.decide = decide
        self.turns: list[str] = []
        self.decisions: list[bool] = []
        self.interrupted = False
        self.closed = False

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        self.turns.append(text)
        for item in self.script:
            if isinstance(item, PermissionRequest):
                self.decisions.append(await self.decide(item))
            else:
                yield item

    async def interrupt(self) -> None:
        self.interrupted = True

    async def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, script=None, fail_open: Exception | None = None) -> None:
        self.id = "fake"
        self.label = "Fake"
        self.supports_modes = True
        self.script = script if script is not None else [ReplyDone("Done.")]
        self.fail_open = fail_open
        self.opened: list[tuple[str, Path]] = []
        self.conversations: list[ScriptedConversation] = []
        self.modes: list = []
        self.toolboxes: list = []

    def models(self) -> list[ModelOption]:
        return [ModelOption("small", "Small"), ModelOption("large", "Large")]

    async def check(self) -> BackendStatus:
        return BackendStatus("not_configured", "Log in first")

    async def open(self, model, cwd, decide_permission, *, mode=None, toolbox=None):
        if self.fail_open is not None:
            raise self.fail_open
        self.opened.append((model, cwd))
        self.modes.append(mode)
        self.toolboxes.append(toolbox)
        conversation = ScriptedConversation(self.script, decide_permission)
        self.conversations.append(conversation)
        return conversation


def _app(backend=None, *, heard="list the files", picked: str | None = "C:/work"):
    backend = backend or FakeBackend()
    channel = FakeChannel()
    loader = FakeLoader(heard)
    app = AgentApp(
        channel=channel,
        registry=BackendRegistry([backend]),
        loader=loader,
        folder_picker=lambda: picked,
    )
    return app, channel, backend, loader


async def _finish_turn(app: AgentApp, channel: FakeChannel) -> None:
    """Let the background turn run, acknowledging every clip the page would play."""
    for _ in range(200):
        played = len(channel.of_type("tts_audio"))
        while app.acknowledged_clips < played:
            app.handle_playback_done()
        if app.turn_task is None or app.turn_task.done():
            break
        await asyncio.sleep(0)
    assert app.turn_task is not None
    await asyncio.wait_for(app.turn_task, timeout=2)


async def test_hello_lists_backends_with_status_and_default_selection():
    app, channel, _, _ = _app()

    await app.handle_hello()

    message = channel.of_type("agent_backends")[0]
    assert message["backends"] == [{
        "id": "fake",
        "label": "Fake",
        "models": [{"id": "small", "label": "Small"}, {"id": "large", "label": "Large"}],
        "status": {"state": "not_configured", "message": "Log in first"},
        "supports_modes": True,
    }]
    assert message["default"] == {"backend": "fake", "model": "small"}
    assert message["session"] is None


async def test_hello_reports_the_running_session_so_a_reconnected_page_can_resync(tmp_path):
    app, channel, _, _ = _app()
    await app.handle_start("fake", "large", str(tmp_path))

    await app.handle_hello()

    assert channel.of_type("agent_backends")[-1]["session"] == {
        "backend": "fake", "model": "large", "cwd": str(tmp_path), "mode": "agent",
    }


async def test_a_failed_start_leaves_no_session_behind(tmp_path):
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)
    await app.handle_start("fake", "small", str(tmp_path))
    backend.fail_open = RuntimeError("CLI missing")
    await app.handle_start("fake", "large", str(tmp_path))

    await app.handle_hello()

    assert channel.of_type("agent_backends")[-1]["session"] is None


@pytest.mark.parametrize("picked", ["C:/work", None])
async def test_pick_folder_reports_the_chosen_path_or_cancel(picked):
    app, channel, _, _ = _app(picked=picked)

    await app.handle_pick_folder()

    assert channel.of_type("agent_folder") == [{"type": "agent_folder", "path": picked}]


async def test_start_opens_the_selected_model_in_the_folder(tmp_path):
    app, channel, backend, _ = _app()

    await app.handle_start("fake", "large", str(tmp_path))

    assert backend.opened == [("large", tmp_path)]
    assert channel.of_type("agent_started") == [{
        "type": "agent_started", "backend": "fake", "model": "large", "cwd": str(tmp_path),
        "mode": "agent",
    }]
    assert channel.sent[-1] == {"type": "state", "state": "listening"}


async def test_start_announces_before_open_and_delivers_queued_text_once(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def slow_open(model, cwd, decide, **kw):
        entered.set()
        await release.wait()
        return await FakeBackend.open(backend, model, cwd, decide, **kw)

    backend.open = slow_open
    await asyncio.wait_for(app.handle_start("fake", "small", str(tmp_path)), timeout=0.1)
    assert channel.of_type("agent_started")
    assert channel.of_type("state")[-1]["state"] == "idle"
    assert entered.is_set() and not release.is_set()
    await app.handle_turn_text("hello before ready")
    assert channel.of_type("state")[-1]["state"] == "thinking"
    await entered.wait()
    assert not backend.conversations
    release.set()
    for _ in range(50):
        if backend.conversations:
            break
        await asyncio.sleep(0)
    await _finish_turn(app, channel)

    assert backend.conversations[0].turns == ["hello before ready"]
    assert len(channel.of_type("agent_reply")) == 1


async def test_second_turn_while_start_and_one_turn_are_pending_is_refused(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def slow_open(model, cwd, decide, **kw):
        entered.set()
        await release.wait()
        return await FakeBackend.open(backend, model, cwd, decide, **kw)

    backend.open = slow_open
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("first")
    await app.handle_turn_text("second")
    assert len(channel.of_type("notice")) == 1
    await entered.wait()
    release.set()
    for _ in range(50):
        if backend.conversations:
            break
        await asyncio.sleep(0)
    await _finish_turn(app, channel)

    assert backend.conversations[0].turns == ["first"]


async def test_audio_turn_can_be_transcribed_and_queued_during_startup(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend, heard="list files")

    async def slow_open(model, cwd, decide, **kw):
        entered.set()
        await release.wait()
        return await FakeBackend.open(backend, model, cwd, decide, **kw)

    backend.open = slow_open
    await app.handle_start("fake", "small", str(tmp_path))
    await entered.wait()
    await app.handle_turn_audio(base64.b64encode(_wav()).decode())
    assert channel.of_type("transcript") == [{
        "type": "transcript", "text": "list files", "final": True,
    }]
    release.set()
    for _ in range(50):
        if backend.conversations:
            break
        await asyncio.sleep(0)
    await _finish_turn(app, channel)

    assert backend.conversations[0].turns == ["list files"]


async def test_interrupt_cancels_pending_start_and_stale_open_is_closed(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def slow_open(model, cwd, decide, **kw):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            await release.wait()  # emulate a provider that suppresses cancellation
        return await FakeBackend.open(backend, model, cwd, decide, **kw)

    backend.open = slow_open
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("discard on interrupt")
    await entered.wait()
    await app.handle_interrupt()
    release.set()
    for _ in range(50):
        if backend.conversations and backend.conversations[0].closed:
            break
        await asyncio.sleep(0)

    assert backend.conversations[0].closed
    assert not channel.of_type("agent_reply")


async def test_interrupt_pending_start_resyncs_session_before_retry(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)
    open_count = 0

    async def open_with_stale_completion(model, cwd, decide, **kw):
        nonlocal open_count
        open_count += 1
        if open_count == 1:
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                await release.wait()
        return await FakeBackend.open(backend, model, cwd, decide, **kw)

    backend.open = open_with_stale_completion
    await app.handle_start("fake", "small", str(tmp_path))
    await entered.wait()
    await app.handle_turn_text("discarded pending turn")
    await app.handle_interrupt()

    assert channel.of_type("agent_backends")[-1]["session"] is None
    assert channel.of_type("state")[-1]["state"] == "idle"
    await app.handle_start("fake", "large", str(tmp_path))
    await app.handle_turn_text("retry turn")
    for _ in range(50):
        if backend.conversations:
            break
        await asyncio.sleep(0)
    await _finish_turn(app, channel)
    release.set()
    for _ in range(50):
        if len(backend.conversations) == 2 and backend.conversations[1].closed:
            break
        await asyncio.sleep(0)

    assert backend.conversations[0].turns == ["retry turn"]
    assert backend.conversations[1].closed


async def test_failed_pending_start_resyncs_session_and_discards_server_queue(tmp_path):
    entered = asyncio.Event()
    release = asyncio.Event()
    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def failed_open(model, cwd, decide, **kw):
        entered.set()
        await release.wait()
        raise RuntimeError("CLI missing")

    backend.open = failed_open
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("retained by the page")
    await entered.wait()
    release.set()
    for _ in range(50):
        if channel.of_type("agent_error"):
            break
        await asyncio.sleep(0)

    await app.handle_hello()
    assert "CLI missing" in channel.of_type("agent_error")[-1]["message"]
    assert channel.of_type("agent_backends")[-1]["session"] is None
    assert channel.of_type("state")[-1]["state"] == "idle"


@pytest.mark.parametrize(
    ("backend_id", "model", "folder_exists"),
    [("missing", "small", True), ("fake", "missing", True), ("fake", "small", False)],
)
async def test_start_rejects_unknown_selection_or_missing_folder(tmp_path, backend_id, model, folder_exists):
    app, channel, backend, _ = _app()
    folder = tmp_path if folder_exists else tmp_path / "nope"

    await app.handle_start(backend_id, model, str(folder))

    assert backend.opened == []
    assert len(channel.of_type("agent_error")) == 1
    assert channel.of_type("agent_started") == []


async def test_start_failure_is_reported_as_agent_error(tmp_path):
    app, channel, _, _ = _app(FakeBackend(fail_open=RuntimeError("CLI missing")))

    await app.handle_start("fake", "small", str(tmp_path))

    errors = channel.of_type("agent_error")
    assert len(errors) == 1 and "CLI missing" in errors[0]["message"]


async def test_new_start_closes_the_previous_conversation(tmp_path):
    app, _, backend, _ = _app()

    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_start("fake", "large", str(tmp_path))

    assert backend.conversations[0].closed
    assert not backend.conversations[1].closed


async def test_turn_before_start_is_rejected():
    app, channel, _, _ = _app()

    await app.handle_turn_text("hello")

    assert app.turn_task is None
    assert len(channel.of_type("agent_error")) == 1


async def test_text_turn_streams_events_and_speaks_the_clean_reply(tmp_path):
    script = [
        TextDelta("Looking."),
        ToolActivity("Read", "app.py"),
        ReplyDone("It has `ExamApp`:\n```py\nclass ExamApp: ...\n```"),
    ]
    app, channel, backend, loader = _app(FakeBackend(script))
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_text("what is in app.py?")
    await _finish_turn(app, channel)

    assert backend.conversations[0].turns == ["what is in app.py?"]
    kinds = [m["type"] for m in channel.sent if m["type"] != "state"]
    assert kinds == ["agent_text", "agent_tool", "agent_reply", "tts_audio"]
    assert channel.of_type("agent_tool")[0] == {"type": "agent_tool", "tool": "Read", "summary": "app.py"}
    assert channel.of_type("agent_reply")[0]["text"].startswith("It has `ExamApp`")
    assert loader.tts.spoken == ["It has ExamApp:"]
    states = [m["state"] for m in channel.of_type("state")]
    assert states == ["thinking", "speaking", "listening"]


async def test_reply_with_nothing_to_speak_skips_tts(tmp_path):
    app, channel, _, loader = _app(FakeBackend([ReplyDone("```\nls\n```")]))
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_text("show me")
    await _finish_turn(app, channel)

    assert loader.tts.spoken == []
    assert [m["state"] for m in channel.of_type("state")] == ["thinking", "listening"]


async def test_agent_error_is_forwarded_and_returns_to_listening(tmp_path):
    app, channel, _, _ = _app(FakeBackend([AgentError("Rate limited")]))
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_text("hi")
    await _finish_turn(app, channel)

    assert channel.of_type("agent_error") == [{"type": "agent_error", "message": "Rate limited"}]
    assert channel.sent[-1] == {"type": "state", "state": "listening"}


async def test_audio_turn_is_transcribed_shown_and_sent(tmp_path):
    app, channel, backend, _ = _app(heard="list the files")
    await app.handle_start("fake", "small", str(tmp_path))

    await app.handle_turn_audio(base64.b64encode(_wav(0.5)).decode())
    await _finish_turn(app, channel)

    assert channel.of_type("transcript") == [{"type": "transcript", "text": "list the files", "final": True}]
    assert backend.conversations[0].turns == ["list the files"]


async def test_unclear_audio_asks_to_repeat_without_a_turn(tmp_path):
    app, channel, backend, _ = _app(heard="")
    await app.handle_start("fake", "small", str(tmp_path))

    await app.handle_turn_audio(base64.b64encode(_wav(0.5)).decode())

    assert app.turn_task is None
    assert len(channel.of_type("notice")) == 1
    assert backend.conversations[0].turns == []


async def test_second_turn_while_one_runs_is_refused(tmp_path):
    gate = asyncio.Event()

    class Slow(ScriptedConversation):
        async def send(self, text):
            self.turns.append(text)
            await gate.wait()
            yield ReplyDone("ok")

    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def open_slow(model, cwd, decide, **kw):
        conversation = Slow([], decide)
        backend.conversations.append(conversation)
        return conversation

    backend.open = open_slow
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("first")
    await asyncio.sleep(0)

    await app.handle_turn_text("second")

    assert backend.conversations[0].turns == ["first"]
    assert len(channel.of_type("notice")) == 1
    gate.set()
    await _finish_turn(app, channel)


async def _run_permission_turn(tmp_path, answer):
    request = PermissionRequest("req-1", "Bash", "Run git status", "git status")
    backend = FakeBackend([request, ReplyDone("ok")])
    app, channel, _, _ = _app(backend)
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("status please")
    for _ in range(50):
        if channel.of_type("permission_request"):
            break
        await asyncio.sleep(0)
    await answer(app)
    await _finish_turn(app, channel)
    return channel, backend.conversations[0]


async def test_permission_request_is_shown_and_allowed(tmp_path):
    async def allow(app):
        await app.handle_permission_response("req-1", True)

    channel, conversation = await _run_permission_turn(tmp_path, allow)

    assert channel.of_type("permission_request") == [{
        "type": "permission_request", "id": "req-1", "tool": "Bash",
        "title": "Run git status", "detail": "git status",
    }]
    assert conversation.decisions == [True]


async def test_permission_denied_by_the_page(tmp_path):
    async def deny(app):
        await app.handle_permission_response("req-1", False)

    _, conversation = await _run_permission_turn(tmp_path, deny)

    assert conversation.decisions == [False]


async def test_pending_permission_is_denied_when_the_page_disconnects(tmp_path):
    async def disconnect(app):
        await app.handle_disconnect()

    _, conversation = await _run_permission_turn(tmp_path, disconnect)

    assert conversation.decisions == [False]


async def test_permission_is_denied_without_a_connected_page(tmp_path):
    async def nothing(app):
        pass

    request = PermissionRequest("req-1", "Bash", "Run", "")
    app, channel, backend, _ = _app(FakeBackend([request, ReplyDone("ok")]))
    channel.is_connected = False
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("go")
    await _finish_turn(app, channel)

    assert backend.conversations[0].decisions == [False]
    assert channel.of_type("permission_request") == []


async def test_interrupt_reaches_the_running_conversation(tmp_path):
    gate = asyncio.Event()

    class Slow(ScriptedConversation):
        async def send(self, text):
            await gate.wait()
            yield ReplyDone("ok")

    backend = FakeBackend()
    app, channel, _, _ = _app(backend)

    async def open_slow(model, cwd, decide, **kw):
        conversation = Slow([], decide)
        backend.conversations.append(conversation)
        return conversation

    backend.open = open_slow
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("long task")
    await asyncio.sleep(0)

    await app.handle_interrupt()

    assert backend.conversations[0].interrupted
    gate.set()
    await _finish_turn(app, channel)


async def test_restart_cancels_the_running_turn_and_withdraws_its_prompt(tmp_path):
    request = PermissionRequest("req-1", "Bash", "Run", "")
    backend = FakeBackend([request, ReplyDone("old reply")])
    app, channel, _, _ = _app(backend)
    await app.handle_start("fake", "small", str(tmp_path))
    await app.handle_turn_text("go")
    for _ in range(50):
        if channel.of_type("permission_request"):
            break
        await asyncio.sleep(0)
    old_turn = app.turn_task
    backend.script = [ReplyDone("new reply")]

    await app.handle_start("fake", "large", str(tmp_path))

    assert old_turn.done()
    first = backend.conversations[0]
    assert first.interrupted and first.closed
    assert channel.of_type("permission_closed") == [{"type": "permission_closed", "id": "req-1"}]
    after_start = channel.sent[channel.sent.index(channel.of_type("agent_started")[-1]):]
    assert all(m["type"] != "agent_reply" for m in after_start)
    await app.handle_turn_text("new turn")
    await _finish_turn(app, channel)
    assert backend.conversations[1].turns == ["new turn"]


async def test_unreadable_audio_reports_an_error_and_keeps_listening(tmp_path):
    app, channel, backend, _ = _app()
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_audio("not base64!!")

    assert len(channel.of_type("agent_error")) == 1
    assert channel.sent[-1] == {"type": "state", "state": "listening"}
    assert backend.conversations[0].turns == []


async def test_transcription_failure_reports_an_error_and_keeps_listening(tmp_path):
    app, channel, _, loader = _app()

    def broken(wav, glossary):
        raise RuntimeError("CUDA out of memory")

    loader.stt.transcribe_with_glossary = broken
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_audio(base64.b64encode(_wav(0.5)).decode())

    assert len(channel.of_type("agent_error")) == 1
    assert channel.sent[-1] == {"type": "state", "state": "listening"}


async def test_blank_text_turn_is_ignored(tmp_path):
    app, channel, backend, _ = _app()
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()

    await app.handle_turn_text("   ")

    assert app.turn_task is None
    assert channel.sent == []
