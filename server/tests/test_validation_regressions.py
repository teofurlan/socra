"""T2 validation regressions; fake speech ports, real WebSocket transport."""
import asyncio
import base64
import json
import re
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import tomllib

import pytest
from websockets.asyncio.client import connect

from socra_server.adapters import piper_tts, whisper_stt
from tests.conftest import free_ports, make_wav_bytes
from tests.test_ws_protocol import ws_bundle, _collect


def test_runtime_dependencies_and_dev_group():
    from socra_server.entrypoints.mcp_tools import create_mcp

    assert create_mcp().name == "socra-server"
    config = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text())
    assert config["dependency-groups"]["dev"]
    assert "dev-dependencies" not in config.get("tool", {}).get("uv", {})


def test_default_stack_path(monkeypatch):
    monkeypatch.delenv("VOICE_STACK_DIR", raising=False)
    expected = (Path(__file__).resolve().parents[2] / "voice").resolve()
    assert piper_tts._voice_stack_dir() == expected
    assert whisper_stt._voice_stack_dir() == expected


@pytest.mark.asyncio
async def test_question_glossary_reaches_recognizer(ws_bundle):
    async with connect(ws_bundle.url) as ws:
        await ws.recv()
        await ws_bundle.app.ask("Q?", 1, 2, glossary=["page table", "TLB"])
        await _collect(ws, 4)
        await ws.send(json.dumps({"type": "answer_audio", "format": "wav", "data": base64.b64encode(make_wav_bytes()).decode()}))
        assert json.loads(await ws.recv()) == {"type": "transcript", "text": "fake transcript", "final": True}
        assert ws_bundle.app.loader.stt.last_extra_glossary == ["page table", "TLB"]
        assert await ws_bundle.app.get_answer(1) == {"status": "answered", "index": 1, "text": "fake transcript"}


@pytest.mark.asyncio
async def test_non_object_and_invalid_audio_messages_are_ignored(ws_bundle, caplog):
    async with connect(ws_bundle.url) as ws:
        await ws.recv()
        await ws_bundle.app.ask("Q?", 1, 2)
        await _collect(ws, 4)
        for message in [[], None, 1, {"type": "answer_audio", "format": "mp3", "data": "AAAA"}, {"type": "answer_audio", "format": "wav", "data": "!!"}]:
            await ws.send(json.dumps(message))
        await ws.send(json.dumps({"type": "reanswer"}))
        assert json.loads(await asyncio.wait_for(ws.recv(), 1)) == {"type": "state", "state": "listening"}
        assert not ws_bundle.app.session.has_answer_for(1)
        assert caplog.records


@pytest.mark.asyncio
async def test_replacement_closes_old_page_and_preserves_new_channel(ws_bundle):
    async with connect(ws_bundle.url) as old:
        await old.recv()
        async with connect(ws_bundle.url) as new:
            assert json.loads(await new.recv()) == {"type": "state", "state": "idle"}
            await asyncio.wait_for(old.wait_closed(), 1)
            assert await ws_bundle.app.say("new page") == {"status": "ok"}
            messages = await _collect(new, 2)
            assert messages[0] == {"type": "state", "state": "speaking"}
            assert base64.b64decode(messages[1]["data"], validate=True) == make_wav_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate", ["reanswer", "question", "replacement"])
async def test_inflight_audio_cannot_restore_discarded_answer(ws_bundle, invalidate):
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = ws_bundle.app.loader.stt.transcribe_with_glossary

    def blocked(*args):
        loop.call_soon_threadsafe(started.set)
        assert release.wait(3)
        return original(*args)

    ws_bundle.app.loader.stt.transcribe_with_glossary = blocked
    async with connect(ws_bundle.url) as ws:
        await ws.recv()
        await ws_bundle.app.ask("Q?", 1, 2)
        await _collect(ws, 4)
        waiting = asyncio.create_task(ws_bundle.app.get_answer(1))
        try:
            await ws.send(json.dumps({"type": "answer_audio", "format": "wav", "data": base64.b64encode(make_wav_bytes()).decode()}))
            await asyncio.wait_for(started.wait(), 1)
            if invalidate == "reanswer":
                await ws.send(json.dumps({"type": "reanswer"}))
                assert json.loads(await asyncio.wait_for(ws.recv(), .5)) == {"type": "state", "state": "listening"}
            elif invalidate == "question":
                await ws_bundle.app.ask("New?", 2, 2)
                await _collect(ws, 4)
            else:
                async with connect(ws_bundle.url) as new:
                    await new.recv()
                    await asyncio.wait_for(ws.wait_closed(), .5)
            release.set()
            assert await waiting == {"status": "listening"}
            assert not ws_bundle.app.session.has_answer_for(ws_bundle.app.session.question_index)
        finally:
            release.set()
            await waiting


@pytest.mark.asyncio
async def test_answer_arrives_while_get_answer_waits(ws_bundle):
    async with connect(ws_bundle.url) as ws:
        await ws.recv()
        await ws_bundle.app.ask("Q?", 1, 1)
        await _collect(ws, 4)
        waiting = asyncio.create_task(ws_bundle.app.get_answer(1))
        await ws.send(json.dumps({"type": "answer_audio", "format": "wav", "data": base64.b64encode(make_wav_bytes()).decode()}))
        assert await waiting == {"status": "answered", "index": 1, "text": "fake transcript"}
        messages = await _collect(ws, 2)
        assert messages == [{"type": "transcript", "text": "fake transcript", "final": True}, {"type": "state", "state": "thinking"}]


@pytest.mark.asyncio
async def test_mcp_handshake_does_not_wait_for_noisy_models():
    code = '''
import os, threading
from socra_server.app import ExamApp

release_models = threading.Event()
original_say = ExamApp.say
async def release_on_say(self, text):
    release_models.set()
    return await original_say(self, text)
ExamApp.say = release_on_say
from socra_server.adapters.piper_tts import PiperTTS
from socra_server.adapters.whisper_stt import WhisperSTT

def noisy_load(self):
    print("PYTHON MODEL OUTPUT", flush=True)
    os.write(1, b"NATIVE MODEL OUTPUT\\n")
    import warnings, logging
    warnings.warn("MODEL WARNING")
    logging.warning("MODEL LOG")
    if __import__("sys").platform == "win32":
        import ctypes
        kernel = ctypes.windll.kernel32
        kernel.GetStdHandle.restype = ctypes.c_void_p
        data = b"WIN32 MODEL OUTPUT\\n"
        written = ctypes.c_ulong()
        assert kernel.WriteFile(ctypes.c_void_p(kernel.GetStdHandle(-11)), data, len(data), ctypes.byref(written), None)
    print("MODEL_LOADING", file=__import__("sys").stderr, flush=True)
    assert release_models.wait(30), "Models were not released by the MCP client"
PiperTTS.load = noisy_load
WhisperSTT.load = noisy_load
from socra_server.__main__ import main
main()
'''
    # Free ports of its own: a running Socra must not decide the page URL.
    ws_port, http_port = free_ports(2)
    env = {**os.environ, "SOCRA_WS_PORT": str(ws_port), "SOCRA_HTTP_PORT": str(http_port)}
    proc = await asyncio.create_subprocess_exec(sys.executable, "-c", code, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    try:
        startup_stderr = bytearray()
        async with asyncio.timeout(60):
            while b"MODEL_LOADING" not in startup_stderr:
                line = await proc.stderr.readline()
                assert line, "Server exited before model loading"
                startup_stderr.extend(line)
        before = time.perf_counter()
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "validation", "version": "1"}}}) + "\n").encode())
        await proc.stdin.drain()
        line = await asyncio.wait_for(proc.stdout.readline(), 2.5)
        assert line, (await proc.stderr.read()).decode()
        response = json.loads(line)
        assert response["id"] == 1
        assert response["result"]["serverInfo"]["name"] == "socra-server"
        assert time.perf_counter() - before < 2.5
        proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}\n')
        await proc.stdin.drain()
        tools = json.loads(await asyncio.wait_for(proc.stdout.readline(), 1))
        assert {tool["name"] for tool in tools["result"]["tools"]} == {"say", "ask", "explain", "get_answer", "open_page", "finish"}
        # Release the fake loaders only after initialize and tools/list have
        # completed, proving neither request awaited model readiness.
        proc.stdin.write(b'{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"say","arguments":{"text":"hello"}}}\n')
        await proc.stdin.drain()
        called = json.loads(await asyncio.wait_for(proc.stdout.readline(), 2.5))
        assert called["id"] == 3
        payload = json.loads(called["result"]["content"][0]["text"])
        # The exact ports are covered in-process (test_port_fallback); here
        # another process may grab a picked port before the server starts.
        expected = {"status": "no_client", "url": payload.get("url")}
        if not (Path(__file__).resolve().parents[2] / "web/dist/index.html").is_file():
            expected["hint"] = "run pnpm -C web build"
        assert payload == expected
        assert re.fullmatch(r"http://localhost:\d+/(\?ws=\d+)?", payload["url"])
        proc.stdin.close()
        # Drain both pipes while waiting; Process.wait() alone can deadlock
        # when subprocess stderr fills its pipe buffer on Windows.
        stdout_tail, stderr_tail = await asyncio.wait_for(proc.communicate(), 10)
        assert stdout_tail == b""
        stderr = startup_stderr.decode(errors="replace") + stderr_tail.decode(errors="replace")
        assert "PYTHON MODEL OUTPUT" in stderr
        assert "NATIVE MODEL OUTPUT" in stderr
        assert "MODEL WARNING" in stderr
        assert "MODEL LOG" in stderr
        if sys.platform == "win32":
            assert "WIN32 MODEL OUTPUT" in stderr
        assert proc.returncode == 0
    finally:
        if proc.returncode is None:
            if sys.platform == "win32":
                # A venv python.exe may launch a child interpreter on Windows.
                killer = await asyncio.create_subprocess_exec(
                    "taskkill", "/PID", str(proc.pid), "/T", "/F",
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                await killer.wait()
            else:
                proc.kill()
            await proc.wait()
