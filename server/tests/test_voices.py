"""Tests for the voice catalogue and the WS voice protocol."""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from socra_server.app import ExamApp, PageChannel
from socra_server.domain.voices import (
    DEFAULT_VOICE_ID,
    VOICES,
    Voice,
    get_voice,
)
from socra_server.entrypoints import ws_server as ws_mod
from tests.conftest import FakeLoader


# ---------------------------------------------------------------------------
# 1. Domain catalogue tests
# ---------------------------------------------------------------------------

def test_voice_catalogue_structure():
    assert len(VOICES) >= 1
    ids = [v.id for v in VOICES]
    assert len(ids) == len(set(ids)), "Voice ids must be unique"

    assert DEFAULT_VOICE_ID == "ryan"
    default_voice = get_voice(DEFAULT_VOICE_ID)
    assert default_voice is not None
    assert default_voice.model == "en/en_US/ryan/high/en_US-ryan-high"
    assert default_voice.length_scale == 1.0
    assert get_voice("daniela") is None  # S2: no Spanish voice is offered

    assert get_voice("nope") is None
    assert get_voice(None) is None
    assert get_voice(123) is None

    # Check that Voice instances are frozen dataclasses
    with pytest.raises(Exception):
        default_voice.id = "new-id"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. WebSocket /ws route tests
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def ws_server_bundle():
    channel = PageChannel()
    loader = FakeLoader()
    app = ExamApp(channel=channel, loader=loader)
    ws_mod.wire_app(app)

    started = asyncio.Event()
    url_holder: list[str] = []

    async def _serve():
        async with serve(
            ws_mod._handle,
            "127.0.0.1",
            0,
            process_request=ws_mod._check_path,
        ) as server:
            host, port = server.sockets[0].getsockname()[:2]
            url_holder.append(f"ws://{host}:{port}/ws")
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(_serve())
    await started.wait()
    try:
        yield url_holder[0], loader
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_ws_voice_messages(ws_server_bundle):
    url, loader = ws_server_bundle
    async with connect(url) as ws:
        # Discard initial state sent on connect
        await ws.recv()

        # 1. Switch to ryan
        await ws.send(json.dumps({"type": "voice", "voice": "ryan"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert len(reply["voices"]) >= 1
        assert reply["voices"] == [{"id": v.id, "label": v.label} for v in VOICES]
        assert loader.tts.voice_id == "ryan"

        # 2. Unknown voice keeps current voice
        await ws.send(json.dumps({"type": "voice", "voice": "nope"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert loader.tts.voice_id == "ryan"

        # 3. Query without voice parameter
        await ws.send(json.dumps({"type": "voice"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert loader.tts.voice_id == "ryan"


@pytest.mark.asyncio
async def test_ws_stored_voice_that_no_longer_exists_falls_back_to_ryan(ws_server_bundle):  # S2
    url, loader = ws_server_bundle
    async with connect(url) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "voice", "voice": "daniela"}))
        reply = json.loads(await ws.recv())
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert loader.tts.voice_id == "ryan"


# ---------------------------------------------------------------------------
# 3. WebSocket /ws/agent route tests
# ---------------------------------------------------------------------------

class _FakeAgentWithLoader:
    def __init__(self, loader: FakeLoader) -> None:
        self.channel = PageChannel()
        self.loader = loader

    async def handle_disconnect(self) -> None:
        pass


@pytest_asyncio.fixture
async def agent_ws_bundle():
    exam = ExamApp(channel=PageChannel(), loader=FakeLoader())
    loader = FakeLoader()
    agent = _FakeAgentWithLoader(loader=loader)
    ws_mod.wire_app(exam)
    ws_mod.wire_agent_app(agent)

    started = asyncio.Event()
    url_holder: list[str] = []

    async def _serve():
        async with serve(
            ws_mod._dispatch,
            "127.0.0.1",
            0,
            process_request=ws_mod._check_path,
        ) as server:
            host, port = server.sockets[0].getsockname()[:2]
            url_holder.append(f"ws://{host}:{port}/ws/agent")
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(_serve())
    await started.wait()
    try:
        yield url_holder[0], loader
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass


@pytest.mark.asyncio
async def test_agent_ws_voice_messages(agent_ws_bundle):
    url, loader = agent_ws_bundle
    async with connect(url) as ws:
        # 1. Switch to ryan
        await ws.send(json.dumps({"type": "voice", "voice": "ryan"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert len(reply["voices"]) >= 1
        assert reply["voices"] == [{"id": v.id, "label": v.label} for v in VOICES]
        assert loader.tts.voice_id == "ryan"

        # 2. Unknown voice keeps current voice
        await ws.send(json.dumps({"type": "voice", "voice": "nope"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert loader.tts.voice_id == "ryan"

        # 3. Query without voice parameter
        await ws.send(json.dumps({"type": "voice"}))
        raw = await ws.recv()
        reply = json.loads(raw)
        assert reply["type"] == "voices"
        assert reply["current"] == "ryan"
        assert loader.tts.voice_id == "ryan"
