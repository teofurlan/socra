"""Run MCP stdio, WebSocket, and loopback HTTP servers in one asyncio loop.

``socra-server --agent`` starts the same WebSocket and HTTP servers without
MCP stdio and opens the agent page; if Socra is already running (for example
as an exam MCP server), it only opens the page.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
import logging
import os
from pathlib import Path
import sys

import anyio
from mcp.server.stdio import stdio_server

from socra_server.adapters.browser import launch_page
from socra_server.adapters.claude_code_agent import ClaudeCodeBackend
from socra_server.adapters.folder_dialog import pick_folder
from socra_server.adapters.pi_agent import PiBackend
from socra_server.adapters.transcript_store import TranscriptStore
from socra_server.agent_app import AgentApp
from socra_server.agent_registry import BackendRegistry
from socra_server.app import ExamApp, ModelLoader, PageChannel
from socra_server.entrypoints import http_server, mcp_tools, ws_server
from socra_server.ports import AgentBackend

LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def _ensure_streams(log_dir: Path = LOG_DIR) -> None:
    """Under pythonw (the desktop shortcut) there is no console: stdout and
    stderr are None, and a library writing to them (a progress bar, a print)
    would crash the server.  Send them to a log file instead."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / "socra-agent.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream


_ensure_streams()

# All logging to stderr — stdout is the JSON-RPC transport
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="%(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


SERVER_PROBE_TIMEOUT_S = 0.5
# Agent mode stops after this long without an agent page, freeing the ports.
AGENT_IDLE_S = float(os.environ.get("SOCRA_AGENT_IDLE_S", "120"))


def agent_backends() -> list[AgentBackend]:
    """The agents the selector offers, in order; the first ready one is the default."""
    return [ClaudeCodeBackend(), PiBackend()]


def _build_apps(loop: asyncio.AbstractEventLoop) -> tuple[ExamApp, AgentApp, ModelLoader]:
    """Wire exam and agent mode to one model loader; each page has its own channel."""
    loader = ModelLoader()
    loader.attach_loop(loop)
    exam = ExamApp(channel=PageChannel(), loader=loader)
    transcripts = TranscriptStore()
    transcripts.prune()
    agent = AgentApp(
        channel=PageChannel(),
        registry=BackendRegistry(agent_backends()),
        loader=loader,
        folder_picker=pick_folder,
        transcripts=transcripts,
    )
    mcp_tools.wire_app(exam)
    ws_server.wire_app(exam)
    ws_server.wire_agent_app(agent)
    return exam, agent, loader


async def server_running(host: str, port: int) -> bool:
    """True when something already listens on the page port (another Socra)."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=SERVER_PROBE_TIMEOUT_S
        )
    except (OSError, TimeoutError):
        return False
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass
    return True


async def _listen(stack: AsyncExitStack, open_server, port: int, name: str) -> int:
    """Bind ``port``, or a free one when another Socra (an agent-mode start or
    another MCP session) holds it, and return the port actually bound."""
    try:
        server = await stack.enter_async_context(open_server(port))
    except OSError as exc:
        logger.warning("%s cannot bind port %d (%s); using a free port", name, port, exc)
        server = await stack.enter_async_context(open_server(0))
    return server.sockets[0].getsockname()[1]


async def open_listeners(
    stack: AsyncExitStack,
    exam: ExamApp,
    *,
    ws_port: int | None = None,
    http_port: int | None = None,
) -> None:
    """Start this process's WebSocket and page servers and point the exam at them,
    so its page always connects back to this process (#26).

    A failure here only costs the page: the MCP tools keep running and report
    no_client with an error and no URL (the default one may be another
    session's page), instead of the whole server dying before the handshake."""
    ws_port = ws_server.WS_PORT if ws_port is None else ws_port
    http_port = http_server.HTTP_PORT if http_port is None else http_port
    try:
        bound_ws = await _listen(
            stack, lambda port: ws_server.serve_pages(port=port), ws_port, "WebSocket server"
        )
        bound_http = await _listen(
            stack, lambda port: http_server.serve_page(dist=exam.web_dist, port=port), http_port, "Page server"
        )
    except Exception:
        logger.exception("Exam page unavailable: could not start its servers")
        exam.page_url = None
        return
    exam.page_url = http_server.page_url(
        bound_http, None if bound_ws == ws_server.PAGE_DEFAULT_WS_PORT else bound_ws
    )
    logger.info("Exam page on %s", exam.page_url)


async def _idle_watch(channel, idle_s: float, poll_s: float = 1.0) -> None:
    """Return once no agent page has been connected for ``idle_s`` seconds."""
    idle = 0.0
    while idle < idle_s:
        await asyncio.sleep(poll_s)
        idle = 0.0 if channel.is_connected else idle + poll_s


async def _standalone(
    launch: Callable[[str], None] = launch_page,
    idle_s: float = AGENT_IDLE_S,
    poll_s: float = 1.0,
) -> None:
    """Agent-mode start: reuse a running Socra, or run HTTP + WebSocket without MCP.

    It stops by itself once no agent page has been open for ``idle_s``, so it
    never keeps the ports an exam MCP server needs.
    """
    if await server_running(http_server.HTTP_HOST, http_server.HTTP_PORT):
        logger.info("Socra is already running; opening the agent page")
        await asyncio.to_thread(launch, http_server.AGENT_PAGE_URL)
        return
    _, agent, loader = _build_apps(asyncio.get_running_loop())
    loader.start()
    ws_task = asyncio.create_task(ws_server.serve_forever(), name="ws-server")
    try:
        async with http_server.serve_page() as server:
            await asyncio.to_thread(launch, http_server.AGENT_PAGE_URL)
            logger.info("Socra agent mode on %s", http_server.AGENT_PAGE_URL)
            serving = asyncio.create_task(server.serve_forever(), name="http-server")
            idle = asyncio.create_task(_idle_watch(agent.channel, idle_s, poll_s), name="idle-watch")
            await asyncio.wait({serving, idle}, return_when=asyncio.FIRST_COMPLETED)
            for task in (serving, idle):
                task.cancel()
            await asyncio.gather(serving, idle, return_exceptions=True)
            logger.info("No agent page for %.0f s; stopping agent mode", idle_s)
    finally:
        ws_task.cancel()
        await asyncio.gather(ws_task, return_exceptions=True)
        await agent.shutdown()


async def _amain(protocol_stdout) -> None:
    loop = asyncio.get_running_loop()

    exam, agent, loader = _build_apps(loop)

    # Build the MCP server
    mcp = mcp_tools.create_mcp()

    # Start model loading in background (non-blocking)
    loader.start()

    try:
        # Network listeners share the MCP loop; binding is immediate and model
        # loading never blocks them.
        async with AsyncExitStack() as listeners:
            await open_listeners(listeners, exam)
            logger.debug("socra-server started; MCP handshake available immediately")

            # Run MCP over stdio (blocks until the client disconnects / process exits)
            # Keep the wire separate from fd 1: native speech libraries may print.
            async with stdio_server(stdout=anyio.wrap_file(protocol_stdout)) as (reader, writer):
                await mcp._mcp_server.run(
                    reader, writer, mcp._mcp_server.create_initialization_options()
                )
    finally:
        await agent.shutdown()


def main() -> None:
    """Console script entry point."""
    if "--agent" in sys.argv[1:]:
        try:
            asyncio.run(_standalone())
        except KeyboardInterrupt:
            pass
        return
    sys.stdout.flush()
    with os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8") as protocol_stdout:
        # Redirect once for the process, not temporarily around worker threads:
        # a temporary redirect could divert concurrent JSON-RPC responses.
        os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
        if sys.platform == "win32":
            import ctypes
            import msvcrt

            ctypes.windll.kernel32.SetStdHandle(
                -11, ctypes.c_void_p(msvcrt.get_osfhandle(sys.stderr.fileno()))
            )
        asyncio.run(_amain(protocol_stdout))


if __name__ == "__main__":
    main()
