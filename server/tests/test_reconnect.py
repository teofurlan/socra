"""Tests for connection survival, reconnect resending, and logging (T5 Change 3)."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import pytest
from websockets.asyncio.client import connect

from socra_server.app import ExamApp, PageChannel
from socra_server.entrypoints.ws_server import WS_PATH, _handle, _check_path
from tests.conftest import FakeLoader, make_wav_bytes


class _FakePage:
    def __init__(self, app=None):
        self.messages = []
        self._app = app
        self._closed = False

    async def send(self, data: str):
        import json
        msg = json.loads(data)
        self.messages.append(msg)
        if self._app and msg.get("type") == "tts_audio":
            self._app.handle_playback_done()

    async def close(self, code=1000, reason=""):
        self._closed = True


def _connect(channel: PageChannel, page: _FakePage) -> None:
    if hasattr(channel, "app") and page._app is None:
        page._app = getattr(channel, "app")
    loop = asyncio.get_running_loop()
    channel.set_connection(page, loop)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_reconnect_resends_question_and_state_without_audio():
    channel = PageChannel()
    loader = FakeLoader()
    app = ExamApp(channel=channel, loader=loader)
    page1 = _FakePage(app=app)
    _connect(channel, page1)

    await app.ask("What is virtual memory?", 2, 5, code="int x = 42;")
    assert app.session.turn_state == "listening"

    # Now simulate a new connection replacing page1 (e.g. page refreshed / reconnected)
    # Using the ws_server connection handler logic:
    # A new page connects:
    from socra_server.entrypoints import ws_server as ws_mod
    ws_mod.wire_app(app)

    # We test via the WebSocket server directly with a real ws client
    from websockets.asyncio.server import serve
    async with serve(
        ws_mod._handle,
        "127.0.0.1",
        0,
        process_request=ws_mod._check_path,
    ) as server:
        host, port = server.sockets[0].getsockname()[:2]
        url = f"ws://{host}:{port}/ws"

        async with connect(url) as ws2:
            import json
            # ws2 should receive the question with code, then the state, with NO tts_audio
            msgs = []
            for _ in range(2):
                raw = await asyncio.wait_for(ws2.recv(), timeout=2.0)
                msgs.append(json.loads(raw))

            q_msg = next((m for m in msgs if m.get("type") == "question"), None)
            assert q_msg is not None
            assert q_msg["text"] == "What is virtual memory?"
            assert q_msg["index"] == 2
            assert q_msg["total"] == 5
            assert q_msg.get("code") == "int x = 42;"

            st_msg = next((m for m in msgs if m.get("type") == "state"), None)
            assert st_msg is not None
            assert st_msg["state"] == "listening"

            # Verify no audio was sent
            assert not any(m.get("type") == "tts_audio" for m in msgs)


@pytest.mark.asyncio
async def test_get_answer_waits_for_reconnection_within_wait_s():
    channel = PageChannel()
    loader = FakeLoader(stt_reply="reconnected answer")
    app = ExamApp(channel=channel, loader=loader)

    # Start with NO page connected
    assert not channel.is_connected

    # Start get_answer with wait_s = 2.0
    task = asyncio.create_task(app.get_answer(wait_s=2.0))
    await asyncio.sleep(0.1)

    # Should not have returned no_client yet
    assert not task.done()

    # Now page connects within the window
    page = _FakePage(app=app)
    _connect(channel, page)
    await asyncio.sleep(0.05)

    # Send answer audio
    import base64
    wav = make_wav_bytes()
    b64 = base64.b64encode(wav).decode()
    await app.handle_answer_audio(b64)

    res = await task
    assert res["status"] == "answered"
    assert res["text"] == "reconnected answer"


@pytest.mark.asyncio
async def test_get_answer_times_out_with_no_client_when_page_does_not_connect():
    channel = PageChannel()
    loader = FakeLoader()
    app = ExamApp(channel=channel, loader=loader)

    assert not channel.is_connected
    res = await app.get_answer(wait_s=1.0)
    assert res["status"] == "no_client"


@pytest.mark.asyncio
async def test_connect_and_disconnect_logged_with_code(tmp_path):
    from socra_server.entrypoints import ws_server as ws_mod
    from websockets.asyncio.server import serve

    log_path = tmp_path / "socra.log"
    handler = ws_mod.setup_file_logging(log_path)

    channel = PageChannel()
    loader = FakeLoader()
    app = ExamApp(channel=channel, loader=loader)
    ws_mod.wire_app(app)

    async with serve(
        ws_mod._handle,
        "127.0.0.1",
        0,
        process_request=ws_mod._check_path,
        ping_interval=20,
        ping_timeout=60,
    ) as server:
        host, port = server.sockets[0].getsockname()[:2]
        url = f"ws://{host}:{port}/ws"

        async with connect(url) as ws:
            await ws.recv()  # receive initial state
            await ws.close(code=1000, reason="Normal test close")

    # Give time for disconnect handler to log
    await asyncio.sleep(0.05)
    handler.flush()
    logging.getLogger("socra_server").removeHandler(handler)
    handler.close()

    # Verify log file exists and contains disconnect info
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "connected" in content.lower()
    assert "disconnected" in content.lower()
    assert "1000" in content
