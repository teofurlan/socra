"""WebSocket server entrypoint — serves ws://localhost:8766/ws (exam) and /ws/agent.

Uses the modern websockets.asyncio API (websockets >= 14).
Binds to 127.0.0.1 only.  One page client at a time; a new connection
replaces the old one.  All logging goes to stderr.
"""
from __future__ import annotations

import asyncio
import json
import logging
import logging.handlers
import os
import sys
from pathlib import Path

from websockets.asyncio.server import serve, ServerConnection
from websockets.http11 import Request, Response

from socra_server.domain.voices import VOICES

LOG_DIR = Path(__file__).resolve().parents[3] / "logs"
LOG_PATH = LOG_DIR / "socra.log"


def _setup_logger() -> logging.Logger:
    ws_logger = logging.getLogger("socra_server.entrypoints.ws_server")
    ws_logger.setLevel(logging.DEBUG)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in ws_logger.handlers):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_PATH, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        ws_logger.addHandler(file_handler)
    if not any(
        isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.handlers.RotatingFileHandler)
        for h in ws_logger.handlers
    ):
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        ws_logger.addHandler(stderr_handler)
    return ws_logger


logger = _setup_logger()

WS_HOST = "127.0.0.1"
# The port the page dials when its URL has no ?ws (web/src/lib/socketUrl.ts).
PAGE_DEFAULT_WS_PORT = 8766
WS_PORT = int(os.environ.get("SOCRA_WS_PORT", str(PAGE_DEFAULT_WS_PORT)))
WS_PATH = "/ws"
AGENT_WS_PATH = "/ws/agent"

# Injected by __main__
_app = None  # type: ignore[assignment]
_agent_app = None  # type: ignore[assignment]


def wire_app(app) -> None:
    global _app
    _app = app


def get_app():
    if _app is None:
        raise RuntimeError("ExamApp not wired — call wire_app() first")
    return _app


def wire_agent_app(app) -> None:
    global _agent_app
    _agent_app = app


def _check_path(connection: ServerConnection, request: Request) -> Response | None:
    """Reject requests whose path is not /ws (exam) or /ws/agent (agent mode)."""
    if request.path not in (WS_PATH, AGENT_WS_PATH):
        return connection.respond(404, "Not found\n")
    return None


async def _dispatch(ws: ServerConnection) -> None:
    """Route each page to its mode's handler by WebSocket path."""
    if ws.request is not None and ws.request.path == AGENT_WS_PATH:
        await _handle_agent(ws)
    else:
        await _handle(ws)


def _agent_text(msg: dict, key: str) -> str | None:
    value = msg.get(key)
    return value if isinstance(value, str) and value else None


def _build_voices_message(tts) -> dict:
    return {
        "type": "voices",
        "voices": [{"id": v.id, "label": v.label} for v in VOICES],
        "current": tts.voice_id,
    }


async def _handle_agent(ws: ServerConnection) -> None:
    """Handle one agent-mode page; a new page replaces the old one."""
    agent = _agent_app
    if agent is None:
        await ws.close(code=1011, reason="Agent mode unavailable")
        return
    loop = asyncio.get_running_loop()

    old = agent.channel._ws
    if old is not None and old is not ws:
        # The new page never saw the old page's permission prompts.
        await agent.handle_disconnect()
    agent.channel.set_connection(ws, loop)
    if old is not None and old is not ws and hasattr(old, "close"):
        try:
            await old.close(code=1000, reason="Replaced by a new page")
        except Exception:
            pass
    background: set[asyncio.Task] = set()

    def spawn(coro, label: str) -> None:
        # Slow work runs beside the read loop, so Allow / Deny answers and
        # interrupts keep flowing while a turn is transcribed or a dialog is open.
        async def guarded() -> None:
            try:
                await coro
            except Exception as exc:
                logger.error("Error handling %s: %s", label, exc)

        task = asyncio.create_task(guarded())
        background.add(task)
        task.add_done_callback(background.discard)

    logger.info("Agent page connected: %s", ws.remote_address)
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception:
                logger.error("Malformed agent message (ignored): %r", raw)
                continue
            if not isinstance(msg, dict):
                logger.warning("Malformed agent message (expected object): %r", msg)
                continue
            if agent.channel._ws is not ws:
                break
            msg_type = msg.get("type")
            try:
                if msg_type == "agent_hello":
                    await agent.handle_hello()
                elif msg_type == "pick_folder":
                    spawn(agent.handle_pick_folder(), msg_type)
                elif msg_type == "start_agent":
                    backend, model, cwd = (_agent_text(msg, k) for k in ("backend", "model", "cwd"))
                    if backend is None or model is None or cwd is None:
                        logger.warning("Malformed start_agent (expected backend, model, cwd)")
                        continue
                    mode = _agent_text(msg, "mode")
                    if mode is None:
                        await agent.handle_start(backend, model, cwd)
                    else:
                        await agent.handle_start(backend, model, cwd, mode=mode)
                elif msg_type == "switch_mode":
                    mode = _agent_text(msg, "mode")
                    if mode is None:
                        logger.warning("Malformed switch_mode (expected mode)")
                        continue
                    spawn(agent.handle_switch_mode(mode), msg_type)
                elif msg_type == "mode_switch_response":
                    mode = _agent_text(msg, "mode")
                    if mode is None:
                        logger.warning("Malformed mode_switch_response (expected mode)")
                        continue
                    await agent.handle_mode_switch_response(mode, msg.get("allow"))
                elif msg_type == "turn_text":
                    text = _agent_text(msg, "text")
                    if text is None:
                        logger.warning("Malformed turn_text (expected text)")
                        continue
                    await agent.handle_turn_text(text)
                elif msg_type == "turn_audio":
                    data = _agent_text(msg, "data")
                    if msg.get("format") != "wav" or data is None:
                        logger.warning("Malformed turn_audio (expected base64 WAV)")
                        continue
                    spawn(agent.handle_turn_audio(data), msg_type)
                elif msg_type == "permission_response":
                    request_id = _agent_text(msg, "id")
                    if request_id is None:
                        logger.warning("Malformed permission_response (expected id)")
                        continue
                    await agent.handle_permission_response(request_id, msg.get("allow"))
                elif msg_type == "interrupt":
                    await agent.handle_interrupt()
                elif msg_type == "playback_done":
                    agent.handle_playback_done()
                elif msg_type == "voice":
                    if "voice" in msg:
                        voice_id = msg["voice"]
                        if not agent.loader.tts.set_voice(voice_id):
                            logger.warning("Unknown voice id (ignored): %r", voice_id)
                    await ws.send(json.dumps(_build_voices_message(agent.loader.tts)))
                else:
                    logger.warning("Unknown agent message type (ignored): %r", msg_type)
            except Exception as exc:
                logger.error("Error handling agent message %r: %s", msg_type, exc)
    except Exception:
        pass
    finally:
        if agent.channel._ws is ws:
            agent.channel.set_connection(None, loop)
            await agent.handle_disconnect()
        if background:
            await asyncio.gather(*background, return_exceptions=True)
        logger.info("Agent page disconnected: %s", ws.remote_address)


async def _handle(ws: ServerConnection) -> None:
    """Handle a single page connection."""
    app = get_app()
    loop = asyncio.get_running_loop()

    # Publish the replacement before closing the old handler.
    old = app.channel._ws
    app.channel.set_connection(ws, loop)
    if old is not None and old is not ws and hasattr(old, "close"):
        try:
            await old.close(code=1000, reason="Replaced by a new page")
        except Exception:
            pass
    audio_tasks: set[asyncio.Task] = set()

    async def transcribe(data: str) -> None:
        try:
            await app.handle_answer_audio(data)
        except Exception as exc:
            logger.error("Error handling answer_audio: %s", exc)
    logger.info("Page connected: %s", ws.remote_address)

    # On a new page connection, resend the current question (with code) and current state (no audio replay).
    try:
        session = app.session
        if session.question_index > 0 and not app._finished:
            q_msg = {
                "type": "question",
                "index": session.question_index,
                "total": session.question_total,
                "text": session.question_text,
            }
            if session.question_code is not None:
                q_msg["code"] = session.question_code
            await ws.send(json.dumps(q_msg))
        await ws.send(json.dumps({"type": "state", "state": session.turn_state}))
        for snapshot_msg in app.walkthrough.snapshot():
            await ws.send(json.dumps(snapshot_msg))
    except Exception as exc:
        logger.error("Failed to send initial messages on connect: %s", exc)

    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except Exception as exc:
                logger.error("Malformed WS message (ignored): %s — %r", exc, raw)
                continue

            if not isinstance(msg, dict):
                logger.warning("Malformed WS message (expected object): %r", msg)
                continue
            if app.channel._ws is not ws:
                break
            msg_type = msg.get("type")
            try:
                if msg_type == "answer_audio":
                    data = msg.get("data")
                    if msg.get("format") != "wav" or not isinstance(data, str) or not data:
                        logger.warning("Malformed answer_audio (expected base64 WAV)")
                        continue
                    task = asyncio.create_task(transcribe(data))
                    audio_tasks.add(task)
                    task.add_done_callback(audio_tasks.discard)
                    # Capture this turn before reading a following reanswer.
                    await asyncio.sleep(0)
                elif msg_type == "answer_text":
                    text = msg.get("text")
                    if not isinstance(text, str):
                        logger.warning("Malformed answer_text (expected text)")
                        continue
                    await app.handle_answer_text(text)
                elif msg_type == "playback_done":
                    seq = msg.get("seq")
                    app.handle_playback_done(seq if isinstance(seq, int) and not isinstance(seq, bool) else None)
                elif msg_type == "walkthrough_control":
                    await app.handle_walkthrough_control(msg.get("action"))
                elif msg_type == "reanswer":
                    await app.handle_reanswer()
                elif msg_type == "mode":
                    await app.handle_mode(msg.get("mode", "auto"))
                elif msg_type == "voice":
                    if "voice" in msg:
                        voice_id = msg["voice"]
                        if not app.loader.tts.set_voice(voice_id):
                            logger.warning("Unknown voice id (ignored): %r", voice_id)
                    await ws.send(json.dumps(_build_voices_message(app.loader.tts)))
                else:
                    logger.warning("Unknown message type (ignored): %r", msg_type)
            except Exception as exc:
                logger.error("Error handling message %r: %s", msg_type, exc)
    except Exception:
        pass
    finally:
        # Clear the connection only if it's still this socket
        if app.channel._ws is ws:
            app.channel.set_connection(None, loop)
            app.handle_page_gone()
        if audio_tasks:
            await asyncio.gather(*audio_tasks)
        close_code = getattr(ws, "close_code", None)
        close_reason = getattr(ws, "close_reason", None) or ""
        logger.info(
            "Page disconnected: %s (code=%s, reason=%r)",
            ws.remote_address,
            close_code,
            close_reason,
        )


def serve_pages(host: str = WS_HOST, port: int = WS_PORT):
    """Bind the page WebSocket server; port=0 picks a free port."""
    return serve(
        _dispatch,
        host,
        port,
        process_request=_check_path,
        ping_interval=20,
        ping_timeout=60,
    )


async def serve_forever(host: str = WS_HOST, port: int = WS_PORT) -> None:
    """Start the WebSocket server and run until cancelled."""
    logger.debug("WebSocket server starting on ws://%s:%d%s", host, port, WS_PATH)
    async with serve_pages(host, port):
        logger.debug("WebSocket server ready on ws://%s:%d%s", host, port, WS_PATH)
        await asyncio.Future()  # run forever


async def serve_on_port(
    host: str, port: int, started_event: asyncio.Event | None = None
) -> None:
    """Serve on an explicit host/port; optionally signal when ready (for tests)."""
    async with serve(_dispatch, host, port, process_request=_check_path) as server:
        if started_event is not None:
            started_event.set()
        await asyncio.Future()
