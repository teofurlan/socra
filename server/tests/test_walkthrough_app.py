"""explain() through ExamApp, the page WebSocket and the MCP tool."""
from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from socra_server.app import ExamApp, PageChannel
from socra_server.entrypoints import mcp_tools, ws_server as ws_mod
from tests.conftest import FakeLoader

CODE = "a = 1\nb = 2\nc = a + b\nprint(c)"
STEPS = [
    {"say": "Two names.", "focus": {"lines": [1, 2]}},
    {"say": "Add them.", "focus": {"lines": [3, 3]}},
]


class FakePage:
    def __init__(self, app: ExamApp, hold: bool = False) -> None:
        self.app = app
        self.hold = hold
        self.messages: list[dict] = []

    async def send(self, data: str) -> None:
        msg = json.loads(data)
        self.messages.append(msg)
        if msg["type"] == "tts_audio" and not self.hold and "step" in msg:
            self.app.handle_playback_done(msg["step"]["seq"])

    def of(self, kind: str) -> list[dict]:
        return [m for m in self.messages if m["type"] == kind]


def connect_page(app: ExamApp, channel: PageChannel, hold: bool = False) -> FakePage:
    page = FakePage(app, hold)
    channel.set_connection(page, asyncio.get_event_loop())  # type: ignore[arg-type]
    return page


async def settle() -> None:
    for _ in range(6):
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_explain_plays_every_step_and_returns_completed(app, channel):
    page = connect_page(app, channel)
    result = await app.explain(CODE, "python", STEPS)
    assert result == {"status": "completed", "steps": 2}
    assert [m["step"]["state"]["code"]["lines"] for m in page.of("tts_audio")] == [[1, 2], [3, 3]]
    assert page.of("walkthrough")[0]["objects"][0]["params"]["code"] == CODE


@pytest.mark.asyncio
async def test_invalid_ranges_are_reported_and_leave_the_page_and_session_alone(app, channel):
    page = connect_page(app, channel)
    bad = STEPS + [{"say": "Oops.", "focus": {"lines": [3, 40]}}]
    result = await app.explain(CODE, "python", bad)
    assert result["status"] == "invalid"
    assert result["errors"][0]["step"] == 3 and "only has 4 lines" in result["errors"][0]["message"]
    assert page.messages == []
    assert not app.walkthrough.active
    assert await app.explain(CODE, "python", STEPS) == {"status": "completed", "steps": 2}


@pytest.mark.asyncio
async def test_explain_without_a_page_is_no_client(app):
    result = await app.explain(CODE, "python", STEPS)
    assert result["status"] == "no_client" and "url" in result


@pytest.mark.asyncio
async def test_paused_voice_command_is_a_walkthrough_command_not_an_answer(app, channel, loader):
    page = connect_page(app, channel, hold=True)
    task = asyncio.create_task(app.explain(CODE, "python", STEPS))
    await settle()
    await app.handle_walkthrough_control("pause")
    await settle()
    assert page.of("walkthrough_status")[-1]["status"] == "paused"

    loader.stt.reply = "repeat that"
    page.hold = False
    await app.handle_answer_audio("AAAA")
    result = await asyncio.wait_for(task, 2)

    assert result == {"status": "completed", "steps": 2}
    assert [m["step"]["index"] for m in page.of("tts_audio")] == [1, 1, 2]
    assert app.session.pending_answer is None
    assert page.of("transcript") == []


@pytest.mark.asyncio
async def test_typed_command_works_and_unknown_speech_gets_a_notice(app, channel):
    page = connect_page(app, channel, hold=True)
    task = asyncio.create_task(app.explain(CODE, "python", STEPS))
    await settle()
    await app.handle_walkthrough_control("pause")
    await settle()

    await app.handle_answer_text("what is a variable")
    assert "repeat" in page.of("notice")[-1]["text"]
    assert page.of("state")[-1]["state"] == "listening"
    assert app.session.pending_answer is None

    await app.handle_answer_text("stop")
    assert (await asyncio.wait_for(task, 2))["status"] == "stopped"


@pytest.mark.asyncio
async def test_unknown_control_actions_are_ignored(app, channel):
    connect_page(app, channel, hold=True)
    task = asyncio.create_task(app.explain(CODE, "python", STEPS))
    await settle()
    await app.handle_walkthrough_control("explode")
    await settle()
    assert not task.done()
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_plain_playback_done_still_completes_say(app, channel):
    page = connect_page(app, channel)
    page.hold = True

    async def done_soon():
        await asyncio.sleep(0.01)
        app.handle_playback_done()

    asyncio.create_task(done_soon())
    assert await app.say("hi") == {"status": "ok"}


@pytest.mark.asyncio
async def test_answers_are_stored_normally_when_no_walkthrough_runs(app, channel):
    connect_page(app, channel)
    await app.handle_answer_text("an answer")
    assert app.session.pending_answer == "an answer"


# ---------------------------------------------------------------------------
# MCP tool and WebSocket
# ---------------------------------------------------------------------------

async def call(mcp, name: str, arguments: dict) -> dict:
    result = await mcp.call_tool(name, arguments)
    content = result[0] if isinstance(result, tuple) else result
    return json.loads(content[0].text)


@pytest.mark.asyncio
async def test_explain_is_an_mcp_tool_that_returns_the_result(app, channel):
    connect_page(app, channel)
    mcp_tools.wire_app(app)
    mcp = mcp_tools.create_mcp()
    assert "explain" in {t.name for t in await mcp.list_tools()}

    payload = await call(mcp, "explain", {"code": CODE, "language": "python", "steps": STEPS})
    assert payload == {"status": "completed", "steps": 2}

    payload = await call(
        mcp,
        "explain", {"code": CODE, "language": "python", "steps": [{"say": "x", "focus": {"lines": [9, 9]}}]}
    )
    assert payload["status"] == "invalid"


@pytest_asyncio.fixture
async def ws_app():
    channel = PageChannel()
    app = ExamApp(channel=channel, loader=FakeLoader())
    ws_mod.wire_app(app)
    started = asyncio.Event()
    urls: list[str] = []

    async def _serve():
        async with serve(ws_mod._handle, "127.0.0.1", 0, process_request=ws_mod._check_path) as server:
            host, port = server.sockets[0].getsockname()[:2]
            urls.append(f"ws://{host}:{port}/ws")
            started.set()
            await asyncio.Future()

    task = asyncio.create_task(_serve())
    await started.wait()
    yield app, urls[0]
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


async def recv_until(ws, kind: str, timeout: float = 3.0) -> dict:
    async with asyncio.timeout(timeout):
        while True:
            msg = json.loads(await ws.recv())
            if msg["type"] == kind:
                return msg


@pytest.mark.asyncio
async def test_page_drives_a_walkthrough_over_the_socket(ws_app):
    app, url = ws_app
    async with connect(url) as ws:
        await recv_until(ws, "state")
        task = asyncio.create_task(app.explain(CODE, "python", STEPS))

        clip = await recv_until(ws, "tts_audio")
        assert clip["step"]["index"] == 1
        await ws.send(json.dumps({"type": "walkthrough_control", "action": "pause"}))
        await ws.send(json.dumps({"type": "playback_done", "seq": clip["step"]["seq"]}))  # stopped clip
        assert (await recv_until(ws, "walkthrough_status"))["status"] == "paused"

        await ws.send(json.dumps({"type": "walkthrough_control", "action": "next"}))
        clip = await recv_until(ws, "tts_audio")
        assert clip["step"]["index"] == 2
        await ws.send(json.dumps({"type": "playback_done", "seq": clip["step"]["seq"]}))
        assert (await asyncio.wait_for(task, 3)) == {"status": "completed", "steps": 2}


@pytest.mark.asyncio
async def test_a_reconnecting_page_gets_the_current_step_and_leaving_ends_the_walkthrough(ws_app):
    app, url = ws_app
    async with connect(url) as first:
        await recv_until(first, "state")
        task = asyncio.create_task(app.explain(CODE, "python", STEPS))
        await recv_until(first, "tts_audio")
        async with connect(url) as second:
            kinds = []
            async with asyncio.timeout(3):
                while "walkthrough_status" not in kinds:
                    kinds.append(json.loads(await second.recv())["type"])
            assert kinds[-3:] == ["walkthrough", "walkthrough_step", "walkthrough_status"]
    result = await asyncio.wait_for(task, 3)
    assert result["status"] == "page_disconnected"


# ---------------------------------------------------------------------------
# present(): any scene, same playback
# ---------------------------------------------------------------------------

SCENE = {
    "version": 1,
    "title": "Adding",
    "objects": [{"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}}],
    "steps": [{"id": "names", "say": "Two names."}, {"id": "sum", "say": "Add them."}],
    "cues": [
        {"at": "names", "do": [{"object": "src", "action": "focus", "params": {"lines": [1, 2]}}]},
        {"at": "sum", "do": [{"object": "src", "action": "focus", "params": {"lines": [3, 3]}}]},
    ],
}


@pytest.mark.asyncio
async def test_present_plays_a_scene_and_returns_completed(app, channel):
    page = connect_page(app, channel)
    result = await app.present(SCENE)
    assert result == {"status": "completed", "steps": 2}
    assert page.of("walkthrough")[0]["title"] == "Adding"
    assert [m["step"]["id"] for m in page.of("tts_audio")] == ["names", "sum"]
    assert [m["step"]["state"]["src"]["lines"] for m in page.of("tts_audio")] == [[1, 2], [3, 3]]


@pytest.mark.asyncio
async def test_an_invalid_scene_is_reported_by_path_and_nothing_is_shown_or_spoken(app, channel):
    page = connect_page(app, channel)
    bad = json.loads(json.dumps(SCENE))
    bad["cues"][1]["do"][0]["params"]["lines"] = [3, 40]
    bad["steps"][0]["say"] = ""
    result = await app.present(bad)
    assert result["status"] == "invalid"
    assert {e["path"] for e in result["errors"]} == {"steps[0].say", "cues[1].do[0].params.lines"}
    assert page.messages == []
    assert not app.walkthrough.active


@pytest.mark.asyncio
async def test_present_is_validated_before_the_page_is_checked(app):
    assert (await app.present({"version": 2}))["status"] == "invalid"
    result = await app.present(SCENE)
    assert result["status"] == "no_client" and "url" in result


@pytest.mark.asyncio
async def test_present_while_a_scene_plays_is_busy(app, channel):
    connect_page(app, channel, hold=True)
    task = asyncio.create_task(app.present(SCENE))
    await settle()
    assert await app.present(SCENE) == {"status": "busy"}
    await app.handle_walkthrough_control("stop")
    assert (await asyncio.wait_for(task, 2))["status"] == "stopped"


@pytest.mark.asyncio
async def test_present_is_an_mcp_tool_that_returns_the_result(app, channel):
    connect_page(app, channel)
    mcp_tools.wire_app(app)
    mcp = mcp_tools.create_mcp()
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "present" in tools
    assert "scene" in tools["present"].inputSchema["properties"]

    assert await call(mcp, "present", {"scene": SCENE}) == {"status": "completed", "steps": 2}
    payload = await call(mcp, "present", {"scene": {"version": 1, "title": "x", "steps": []}})
    assert payload["status"] == "invalid" and payload["errors"][0]["path"] == "steps"
