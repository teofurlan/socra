"""T4 public tool and HTTP contracts; no voice models or browser required."""
from __future__ import annotations

import asyncio
import json
from time import perf_counter
from unittest.mock import Mock

import pytest

from socra_server.app import ExamApp, PageChannel
from socra_server.entrypoints.mcp_tools import create_mcp, wire_app
from tests.conftest import FakeLoader


class Page:
    def __init__(self):
        self.messages = []
        self._app = None

    async def send(self, message):
        msg = json.loads(message)
        self.messages.append(msg)
        if self._app and msg.get("type") == "tts_audio":
            self._app.handle_playback_done()


def connected_app(**kwargs):
    channel = PageChannel()
    page = Page()
    channel.set_connection(page, asyncio.get_running_loop())
    app = ExamApp(channel, FakeLoader(), **kwargs)
    page._app = app
    return app, page


async def tool_call(app, name, arguments):
    wire_app(app)
    result = await create_mcp().call_tool(name, arguments)
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


@pytest.mark.asyncio
async def test_static_files_and_spa_fallback_are_served_on_loopback(tmp_path):
    from socra_server.entrypoints.http_server import serve_page

    (tmp_path / "index.html").write_text("<h1>Exam page</h1>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("console.log('exam')")
    outside = tmp_path.parent / "private.txt"
    outside.write_text("must not be served")
    async with serve_page(dist=tmp_path, port=0) as server:
        host, port = server.sockets[0].getsockname()[:2]
        assert host == "127.0.0.1"

        async def request(path, method="GET"):
            reader, writer = await asyncio.open_connection(host, port)
            try:
                writer.write(f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
                await writer.drain()
                response = await reader.read()
                headers, body = response.split(b"\r\n\r\n", 1)
                return headers.decode(), body
            finally:
                writer.close()
                await writer.wait_closed()

        for path in ("/", "/exam/1?view=code"):
            headers, body = await request(path)
            assert headers.startswith("HTTP/1.1 200")
            assert "Content-Type: text/html" in headers
            assert body == b"<h1>Exam page</h1>"
        headers, body = await request("/assets/app.js")
        assert headers.startswith("HTTP/1.1 200")
        assert "javascript" in headers
        assert body == b"console.log('exam')"
        headers, body = await request("/assets/app.js", "HEAD")
        assert headers.startswith("HTTP/1.1 200") and body == b""
        headers, body = await request("/%2e%2e/private.txt")
        assert headers.startswith("HTTP/1.1 403")
        assert b"must not be served" not in body


@pytest.mark.asyncio
@pytest.mark.parametrize("built", [False, True])
async def test_no_client_url_and_build_hint_for_all_tools(tmp_path, built, monkeypatch):
    if built:
        (tmp_path / "index.html").write_text("exam")
    app = ExamApp(PageChannel(), FakeLoader(), web_dist=tmp_path, launcher=lambda url: None)
    monkeypatch.setattr("socra_server.app.OPEN_PAGE_TIMEOUT_S", 0.01)
    expected = {"status": "no_client", "url": "http://localhost:8767/"}
    if not built:
        expected["hint"] = "run pnpm -C web build"
    for name, args in (("say", {"text": "Hi"}), ("ask", {"question": "Q?", "index": 1, "total": 1}),
                       ("get_answer", {"wait_s": 1}), ("finish", {}), ("open_page", {})):
        assert await tool_call(app, name, args) == expected


@pytest.mark.asyncio
async def test_open_page_reuses_connected_page_without_launching():
    launcher = Mock()
    app, _ = connected_app(launcher=launcher)
    assert await tool_call(app, "open_page", {}) == {"status": "connected"}
    launcher.assert_not_called()


@pytest.mark.asyncio
async def test_open_page_times_out_with_fake_launcher(tmp_path, monkeypatch):
    launcher = Mock()
    app = ExamApp(PageChannel(), FakeLoader(), web_dist=tmp_path, launcher=launcher)
    monkeypatch.setattr("socra_server.app.OPEN_PAGE_TIMEOUT_S", 0.03)
    start = perf_counter()
    assert await tool_call(app, "open_page", {}) == {
        "status": "no_client", "url": "http://localhost:8767/", "hint": "run pnpm -C web build",
    }
    assert perf_counter() - start < 1
    launcher.assert_called_once_with("http://localhost:8767/")


@pytest.mark.asyncio
async def test_open_page_waits_for_connection(monkeypatch):
    app = ExamApp(PageChannel(), FakeLoader(), launcher=lambda url: None)
    monkeypatch.setattr("socra_server.app.OPEN_PAGE_TIMEOUT_S", 0.2)

    async def connect():
        await asyncio.sleep(0.01)
        app.channel.set_connection(Page(), asyncio.get_running_loop())

    connection = asyncio.create_task(connect())
    try:
        assert await tool_call(app, "open_page", {}) == {"status": "connected"}
    finally:
        await connection


@pytest.mark.asyncio
async def test_ask_displays_code_but_synthesizes_only_question():
    app, page = connected_app()
    synthesize = Mock(wraps=app.loader.tts.synthesize)
    app.loader.tts.synthesize = synthesize
    assert await tool_call(app, "ask", {
        "question": "Read this code.", "index": 2, "total": 4,
        "glossary": ["thread"], "code": 'print("DISPLAY_ONLY_7291")',
    }) == {"status": "asked"}
    assert page.messages[0] == {
        "type": "question", "index": 2, "total": 4, "text": "Read this code.",
        "code": 'print("DISPLAY_ONLY_7291")',
    }
    assert [m.get("state") for m in page.messages if m["type"] == "state"] == ["speaking", "listening"]
    synthesize.assert_called_once_with("Read this code.")


@pytest.mark.asyncio
@pytest.mark.parametrize("summary", [None, "You completed the exam."])
async def test_finish_sends_optional_summary_then_idle_and_finished(summary):
    app, page = connected_app()
    synthesize = Mock(wraps=app.loader.tts.synthesize)
    app.loader.tts.synthesize = synthesize
    assert await tool_call(app, "finish", {"summary": summary}) == {"status": "finished"}
    if summary is None:
        synthesize.assert_not_called()
        assert len(page.messages) == 2
    else:
        synthesize.assert_called_once_with(summary)
        assert page.messages[0] == {"type": "state", "state": "speaking"}
        assert page.messages[1]["type"] == "tts_audio"
        assert len(page.messages) == 4
    assert page.messages[-2:] == [{"type": "state", "state": "idle"}, {"type": "finished"}]


@pytest.mark.asyncio
async def test_tool_descriptions_explain_polling_and_verbatim_transcripts():
    tools = {tool.name: tool for tool in await create_mcp().list_tools()}
    assert set(tools) == {"open_page", "say", "ask", "explain", "get_answer", "finish"}
    description = tools["get_answer"].description.lower()
    assert "repeatedly" in description and "listening" in description and "verbatim" in description
    assert "code" in tools["ask"].inputSchema["properties"]
    assert all(tool.description for tool in tools.values())
