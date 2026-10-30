"""Agent-mode WebSocket route: real server on an ephemeral port, fake agent service."""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from socra_server.app import ExamApp, PageChannel
from socra_server.entrypoints import ws_server as ws_mod
from tests.conftest import FakeLoader


class FakeAgentApp:
    """Records every call the route makes; turn_audio can be held open."""

    def __init__(self) -> None:
        self.channel = PageChannel()
        self.calls: list[tuple] = []
        self.audio_gate = asyncio.Event()
        self.audio_gate.set()
        self.called = asyncio.Event()

    def _record(self, *call) -> None:
        self.calls.append(call)
        self.called.set()

    async def handle_hello(self):
        self._record("hello")

    async def handle_pick_folder(self):
        self._record("pick_folder")

    async def handle_start(self, backend, model, cwd, mode=None):
        self._record("start", backend, model, cwd, *([mode] if mode else []))

    async def handle_switch_mode(self, mode):
        self._record("switch_mode", mode)

    async def handle_mode_switch_response(self, mode, allow):
        self._record("mode_switch_response", mode, allow)

    async def handle_turn_text(self, text):
        self._record("turn_text", text)

    async def handle_turn_audio(self, data):
        self._record("turn_audio_started", data)
        await self.audio_gate.wait()
        self._record("turn_audio_done", data)

    async def handle_permission_response(self, request_id, allow):
        self._record("permission", request_id, allow)

    async def handle_interrupt(self):
        self._record("interrupt")

    def handle_playback_done(self, seq=None):
        self._record("playback_done", seq)

    async def handle_walkthrough_control(self, action):
        self._record("walkthrough_control", action)

    async def handle_disconnect(self):
        self._record("disconnect")


@pytest_asyncio.fixture
async def server():
    exam = ExamApp(channel=PageChannel(), loader=FakeLoader())
    agent = FakeAgentApp()
    ws_mod.wire_app(exam)
    ws_mod.wire_agent_app(agent)
    started = asyncio.Event()
    base: list[str] = []

    async def _serve():
        async with serve(ws_mod._dispatch, "127.0.0.1", 0, process_request=ws_mod._check_path) as srv:
            host, port = srv.sockets[0].getsockname()[:2]
            base.append(f"ws://{host}:{port}")
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(_serve())
    await started.wait()
    yield base[0], agent
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def _wait_for(agent: FakeAgentApp, predicate, timeout: float = 3.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            agent.called.clear()
            await agent.called.wait()


async def test_agent_route_dispatches_every_page_message(server):
    base, agent = server
    messages = [
        {"type": "agent_hello"},
        {"type": "pick_folder"},
        {"type": "start_agent", "backend": "claude-code", "model": "opus", "cwd": "C:/work"},
        {"type": "turn_text", "text": "list the files"},
        {"type": "turn_audio", "format": "wav", "data": "UklGRg=="},
        {"type": "permission_response", "id": "req-1", "allow": True},
        {"type": "interrupt"},
        {"type": "playback_done"},
        {"type": "playback_done", "seq": 4},
        {"type": "walkthrough_control", "action": "pause"},
        {"type": "switch_mode", "mode": "exam"},
        {"type": "mode_switch_response", "mode": "mentor", "allow": True},
        {"type": "start_agent", "backend": "claude-code", "model": "opus", "cwd": "C:/w", "mode": "exam"},
        {"type": "switch_mode"},
    ]
    async with connect(f"{base}/ws/agent") as ws:
        for message in messages:
            await ws.send(json.dumps(message))
        await _wait_for(agent, lambda: len(agent.calls) >= 13)

    names = [call[0] for call in agent.calls]
    for expected in ("hello", "pick_folder", "turn_audio_done", "interrupt", "playback_done"):
        assert expected in names
    assert ("start", "claude-code", "opus", "C:/work") in agent.calls
    assert ("turn_text", "list the files") in agent.calls
    assert ("switch_mode", "exam") in agent.calls
    assert ("mode_switch_response", "mentor", True) in agent.calls
    assert ("start", "claude-code", "opus", "C:/w", "exam") in agent.calls
    # A switch_mode without a mode is malformed and dropped.
    assert sum(1 for call in agent.calls if call[0] == "switch_mode") == 1
    assert ("permission", "req-1", True) in agent.calls
    assert ("playback_done", None) in agent.calls and ("playback_done", 4) in agent.calls
    assert ("walkthrough_control", "pause") in agent.calls


async def test_permission_answer_is_not_blocked_by_a_running_transcription(server):
    base, agent = server
    agent.audio_gate.clear()
    async with connect(f"{base}/ws/agent") as ws:
        await ws.send(json.dumps({"type": "turn_audio", "format": "wav", "data": "UklGRg=="}))
        await ws.send(json.dumps({"type": "permission_response", "id": "req-9", "allow": False}))
        await _wait_for(agent, lambda: ("permission", "req-9", False) in agent.calls)

        assert ("turn_audio_done", "UklGRg==") not in agent.calls
        agent.audio_gate.set()
        await _wait_for(agent, lambda: ("turn_audio_done", "UklGRg==") in agent.calls)


async def test_malformed_messages_are_ignored_and_the_socket_stays_open(server):
    base, agent = server
    async with connect(f"{base}/ws/agent") as ws:
        for raw in ("not json", "[1, 2]", json.dumps({"type": "start_agent", "backend": 5}),
                    json.dumps({"type": "turn_audio", "format": "mp3", "data": "x"}),
                    json.dumps({"type": "turn_text", "text": ""}),
                    json.dumps({"type": "nope"})):
            await ws.send(raw)
        await ws.send(json.dumps({"type": "agent_hello"}))
        await _wait_for(agent, lambda: ("hello",) in agent.calls)

    assert agent.calls[0] == ("hello",)


async def test_closing_the_agent_page_denies_pending_requests(server):
    base, agent = server
    async with connect(f"{base}/ws/agent") as ws:
        await ws.send(json.dumps({"type": "agent_hello"}))
        await _wait_for(agent, lambda: ("hello",) in agent.calls)

    await _wait_for(agent, lambda: ("disconnect",) in agent.calls)
    assert not agent.channel.is_connected


async def test_a_new_agent_page_replaces_the_old_one_and_denies_its_requests(server):
    base, agent = server
    async with connect(f"{base}/ws/agent") as first:
        await first.send(json.dumps({"type": "agent_hello"}))
        await _wait_for(agent, lambda: ("hello",) in agent.calls)
        async with connect(f"{base}/ws/agent") as second:
            await _wait_for(agent, lambda: ("disconnect",) in agent.calls)
            await second.send(json.dumps({"type": "interrupt"}))
            await _wait_for(agent, lambda: ("interrupt",) in agent.calls)
            assert agent.channel.is_connected


async def test_exam_route_still_reaches_the_exam_handler(server):
    base, agent = server
    async with connect(f"{base}/ws") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))

    assert first == {"type": "state", "state": "idle"}
    assert agent.calls == []


async def test_unknown_paths_are_rejected(server):
    base, _ = server
    with pytest.raises(InvalidStatus):
        async with connect(f"{base}/ws/other"):
            pass
