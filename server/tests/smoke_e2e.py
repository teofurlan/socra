"""Manual microphone-free MCP/WebSocket smoke using real Piper and Whisper.

Not collected by pytest (the filename deliberately doesn't start with test_).
Run from the repository root after building the page:
    pnpm -C web build
    uv run --project server python server/tests/smoke_e2e.py

Requires the real voice stack/model caches used by the server. Ports 8766 and
8767 must be free. No browser or microphone is opened: a headless WebSocket
client connects before open_page, which must therefore reuse that connection.
Failures are fatal; missing T4 tools are not skipped or replaced by fake ones.
"""
from __future__ import annotations

import asyncio
import base64
from datetime import timedelta
import io
import json
import logging
import os
from pathlib import Path
import socket
import sys
from time import perf_counter
import wave

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from websockets.asyncio.client import connect

from socra_server.adapters.piper_tts import PiperTTS

ROOT = Path(__file__).resolve().parents[2]
QUESTION = "Explain the difference between a process and a thread."
CODE = 'print("DISPLAY_ONLY_7291")'
ANSWER = "A process has its own memory, and a thread shares the memory of its process."


class ProtocolErrors(logging.Handler):
    """Catch SDK diagnostics for non-JSON-RPC bytes on subprocess stdout."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def check_ports_free() -> tuple[int, int]:
    ws_env = os.environ.get("SOCRA_WS_PORT")
    http_env = os.environ.get("SOCRA_HTTP_PORT")
    if ws_env and http_env:
        return int(ws_env), int(http_env)
    for ws_p, http_p in [(8766, 8767), (8866, 8867), (8966, 8967)]:
        try:
            for port in (ws_p, http_p):
                with socket.socket() as probe:
                    # On Windows SO_REUSEADDR can steal an existing listener's port.
                    if sys.platform == "win32":
                        probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    probe.bind(("127.0.0.1", port))
            return ws_p, http_p
        except OSError:
            continue
    raise RuntimeError("No free ports found for smoke server")


async def call(session: ClientSession, name: str, arguments: dict) -> dict:
    result = await session.call_tool(name, arguments)
    text = "\n".join(block.text for block in result.content if block.type == "text")
    assert not result.isError, f"{name} failed: {text}"
    payload = json.loads(text)
    assert isinstance(payload, dict), (name, payload)
    return payload


async def connect_page(ws_port: int):
    # Bound startup retry, not an unbounded wait for model readiness.
    async with asyncio.timeout(15):
        while True:
            try:
                return await connect(f"ws://127.0.0.1:{ws_port}/ws", open_timeout=1)
            except OSError:
                await asyncio.sleep(0.05)


async def exercise(session: ClientSession, ws_port: int) -> None:
    started = perf_counter()
    await session.initialize()
    initialized = perf_counter()
    tools = {tool.name: tool for tool in (await session.list_tools()).tools}
    print(f"MCP tools: {', '.join(sorted(tools))}", flush=True)
    print(f"MCP initialize: {initialized - started:.3f}s", flush=True)

    ws = await connect_page(ws_port)
    try:
        assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {"type": "state", "state": "idle"}
        before_open = perf_counter()
        opened = await asyncio.wait_for(call(session, "open_page", {}), 15)
        assert opened == {"status": "connected"}, opened
        print(f"open_page (already connected): {perf_counter() - before_open:.3f}s", flush=True)
        assert "code" in tools["ask"].inputSchema["properties"], "ask does not advertise code"

        before_ask = perf_counter()
        ask_task = asyncio.create_task(
            call(
                session,
                "ask",
                {
                    "question": QUESTION,
                    "index": 1,
                    "total": 1,
                    "code": CODE,
                },
            )
        )
        m0 = json.loads(await asyncio.wait_for(ws.recv(), 30))
        m1 = json.loads(await asyncio.wait_for(ws.recv(), 5))
        m2 = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert m0 == {
            "type": "question",
            "index": 1,
            "total": 1,
            "text": QUESTION,
            "code": CODE,
        }, m0
        assert m1 == {"type": "state", "state": "speaking"}, m1
        assert m2["type"] == "tts_audio" and m2["format"] == "wav", m2
        with wave.open(io.BytesIO(base64.b64decode(m2["data"], validate=True)), "rb") as wav:
            assert wav.getnframes() > 0

        # Page signals playback finished
        await ws.send(json.dumps({"type": "playback_done"}))

        asked = await asyncio.wait_for(ask_task, 5)
        assert asked == {"status": "asked"}, asked

        m3 = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert m3 == {"type": "state", "state": "listening"}, m3
        asked_at = perf_counter()
        print(f"ask / real question TTS (including model readiness): {asked_at - before_ask:.3f}s", flush=True)

        # A separate, real Piper adapter generates the answer; no fake audio,
        # microphone, cleaner, or precomputed transcript enters the round trip.
        def synthesize_answer() -> bytes:
            tts = PiperTTS()
            tts.load()
            return tts.synthesize(ANSWER)

        answer_wav = await asyncio.to_thread(synthesize_answer)
        synthesized_at = perf_counter()
        with wave.open(io.BytesIO(answer_wav), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            assert duration > 0
        await ws.send(json.dumps({
            "type": "answer_audio", "format": "wav",
            "data": base64.b64encode(answer_wav).decode("ascii"),
        }))
        polls = 0
        async with asyncio.timeout(60):
            while True:
                result = await call(session, "get_answer", {"wait_s": 1})
                polls += 1
                if result.get("status") == "answered":
                    break
                assert result == {"status": "listening"}, result
        answered_at = perf_counter()
        assert result["index"] == 1 and result["text"].strip(), result
        transcript = json.loads(await asyncio.wait_for(ws.recv(), 5))
        assert transcript == {"type": "transcript", "text": result["text"], "final": True}, transcript
        assert json.loads(await asyncio.wait_for(ws.recv(), 5)) == {"type": "state", "state": "thinking"}
        print(f"Transcript: {result['text']}", flush=True)
        print(f"Answer Piper load + synthesis: {synthesized_at - asked_at:.3f}s", flush=True)
        print(f"Answer WAV: {len(answer_wav)} bytes, {duration:.3f}s", flush=True)
        print(f"Whisper + MCP polling: {answered_at - synthesized_at:.3f}s ({polls} polls)", flush=True)
        print(f"Total: {answered_at - started:.3f}s", flush=True)
    finally:
        await ws.close()


async def main() -> None:
    assert (ROOT / "web/dist/index.html").is_file(), "Build the page first: pnpm -C web build"
    ws_port, http_port = check_ports_free()
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "socra_server"],
        cwd=str(ROOT),
        env={
            **{key: os.environ[key] for key in (
                "VOICE_STACK_DIR", "HF_HOME", "HF_HUB_CACHE", "XDG_CACHE_HOME",
            ) if key in os.environ},
            "SOCRA_WS_PORT": str(ws_port),
            "SOCRA_HTTP_PORT": str(http_port),
            "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8",
        },
    )
    errors = ProtocolErrors()
    transport_logger = logging.getLogger("mcp.client.stdio")
    transport_logger.addHandler(errors)
    try:
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=120)) as session:
                async with asyncio.timeout(180):
                    await exercise(session, ws_port)
        assert not errors.messages, f"Subprocess stdout contained non-JSON-RPC output: {errors.messages}"
        print("PASS: real MCP / WebSocket / Piper / Whisper round trip", flush=True)
    finally:
        transport_logger.removeHandler(errors)


if __name__ == "__main__":
    asyncio.run(main())
