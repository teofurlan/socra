"""Pi (gentle-pi) adapter for the AgentBackend port, over ``pi --mode rpc``.

Pi runs as a child process in the chosen folder and speaks JSONL: commands on
stdin, responses and session events on stdout. Pi itself never asks before a
tool call; extensions that do (gentle-pi's guarded commands) send a ``confirm``
dialog, which reaches the PermissionDecider. Everything else follows Pi's own
settings, including gentle-pi's permission mode.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import platform
import re
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any, Protocol

from socra_server.adapters.tool_summary import summarize_tool_input
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
from socra_server.ports import PermissionDecider

logger = logging.getLogger(__name__)

# Loading the user's extensions took 11-56 s before Pi answered (measured).
STARTUP_TIMEOUT_S = 120.0
DISCOVERY_TIMEOUT_S = 30.0
FULL_DISCOVERY_TIMEOUT_S = 180.0
IDLE_TIMEOUT_S = 10.0
CLOSE_TIMEOUT_S = 10.0
STDERR_DRAIN_S = 2.0
# One record can hold a whole run's messages (system prompt included).
STREAM_LIMIT = 64 * 1024 * 1024
# Model discovery only lists models, so it skips what it can.
DISCOVERY_FLAGS = (
    "--no-session", "--no-skills", "--no-mcp",
    "--no-prompt-templates", "--no-themes", "--no-context-files", "--offline",
)
# Without extensions Pi lists its models in ~1 s, but misses the providers that
# extensions add (pi-antigravity); with them it takes ~20 s (measured).
FAST_DISCOVERY_FLAGS = (*DISCOVERY_FLAGS, "--no-extensions")
CACHE_PATH = (
    Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".cache") / "Socra" / "pi-models.json"
)
# Model ids reach the command line (a .cmd wrapper on Windows): keep them plain.
_PROVIDER = re.compile(r"[A-Za-z0-9._-]+")
_MODEL = re.compile(r"[A-Za-z0-9._:@+-]+(?:/[A-Za-z0-9._:@+-]+)*")
_ERROR_MAX = 300
_DIALOGS_WITHOUT_VOICE = ("select", "input", "editor")


class PiRpc(Protocol):
    """One ``pi --mode rpc`` process, as JSON records."""

    async def send(self, record: dict[str, Any]) -> None:
        ...

    async def receive(self) -> dict[str, Any] | None:
        """Return the next record, or None once Pi's output has closed."""
        ...

    async def close(self) -> None:
        ...

    def stderr_tail(self) -> str:
        ...


RpcStarter = Callable[[list[str], Path], Awaitable[PiRpc]]


def find_cli() -> str | None:
    """Prefer a ``pi`` on PATH, then the managed install in ``~/.pi/agent/bin``."""
    name = "pi.cmd" if platform.system() == "Windows" else "pi"
    found = shutil.which(name)
    if found:
        return found
    managed = Path.home() / ".pi" / "agent" / "bin" / name
    return str(managed) if managed.is_file() else None


class SubprocessRpc:
    """JSONL over a child process: records split on LF only, never on U+2028."""

    def __init__(self, process: asyncio.subprocess.Process) -> None:
        self._process = process
        self._stderr: collections.deque[str] = collections.deque(maxlen=20)
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name="pi-stderr")

    @classmethod
    async def start(cls, args: list[str], cwd: Path) -> SubprocessRpc:
        process = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            limit=STREAM_LIMIT,
        )
        return cls(process)

    async def send(self, record: dict[str, Any]) -> None:
        stdin = self._process.stdin
        assert stdin is not None
        stdin.write(json.dumps(record).encode("utf-8") + b"\n")
        await stdin.drain()

    async def receive(self) -> dict[str, Any] | None:
        stdout = self._process.stdout
        assert stdout is not None
        while True:
            try:
                line = await stdout.readline()
            except ValueError as exc:
                logger.warning("Skipped an oversized Pi record: %s", exc)
                continue
            if not line:
                # Let Pi's last words (why it exited) reach stderr_tail().
                await asyncio.wait([self._stderr_task], timeout=STDERR_DRAIN_S)
                return None
            line = line.removesuffix(b"\n").removesuffix(b"\r")
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                logger.debug("Skipped a non-JSON line from Pi: %r", line[:200])
                continue
            if isinstance(record, dict):
                return record

    async def close(self) -> None:
        stdin = self._process.stdin
        if stdin is not None and not stdin.is_closing():
            stdin.close()  # Pi's orderly shutdown
        try:
            await asyncio.wait_for(self._process.wait(), CLOSE_TIMEOUT_S)
        except TimeoutError:
            logger.warning("Pi did not exit after its input closed; killing it")
            self._process.kill()
            await self._process.wait()
        await asyncio.wait([self._stderr_task], timeout=STDERR_DRAIN_S)

    def stderr_tail(self) -> str:
        return "\n".join(self._stderr)

    async def _drain_stderr(self) -> None:
        stderr = self._process.stderr
        assert stderr is not None
        while line := await stderr.readline():
            self._stderr.append(line.decode("utf-8", errors="replace").rstrip())


def _split_model(model: str) -> tuple[str, str]:
    provider, _, model_id = model.partition("/")
    if not (_PROVIDER.fullmatch(provider) and _MODEL.fullmatch(model_id)):
        raise ValueError(f"Not a Pi model id (provider/model): {model!r}")
    return provider, model_id


def _model_option(model: dict[str, Any]) -> ModelOption | None:
    provider, model_id = model.get("provider"), model.get("id")
    if not (isinstance(provider, str) and isinstance(model_id, str) and provider and model_id):
        return None
    name = model.get("name") if isinstance(model.get("name"), str) else model_id
    return ModelOption(f"{provider}/{model_id}", f"{name} ({provider})")


def _readable_error(raw: str) -> str:
    """Pi passes provider errors through as (nested) JSON; keep the innermost message."""
    text = raw
    for _ in range(5):
        try:
            data = json.loads(text)
        except ValueError:
            break
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            data = data["error"]
        message = data.get("message") if isinstance(data, dict) else None
        if not isinstance(message, str):
            break
        text = message
    text = " ".join(text.split())
    return text if len(text) <= _ERROR_MAX else text[: _ERROR_MAX - 1] + "…"


class PiConversation:
    def __init__(self, rpc: PiRpc, decide_permission: PermissionDecider) -> None:
        self._rpc = rpc
        self._decide = decide_permission
        self._waiting: dict[str, asyncio.Future[dict[str, Any]]] = {}
        # Events of the turn in progress; None between turns (stale events are dropped).
        self._events: asyncio.Queue[dict[str, Any] | None] | None = None
        self._idle = asyncio.Event()
        self._idle.set()
        self._exited = False
        self._last_tool = ""
        self._dialogs: dict[str, asyncio.Task[None]] = {}
        self._background: set[asyncio.Task[None]] = set()
        self._reader: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Begin reading and wait until Pi answers, so no turn is sent too early."""
        self._reader = asyncio.create_task(self._read_loop(), name="pi-rpc-reader")
        try:
            response = await asyncio.wait_for(
                self._request({"type": "get_state"}), STARTUP_TIMEOUT_S
            )
        except ConnectionError:
            raise RuntimeError(self._exit_message()) from None
        except TimeoutError:
            raise RuntimeError(f"Pi did not answer within {STARTUP_TIMEOUT_S:.0f} s.") from None
        if not response.get("success"):
            raise RuntimeError(response.get("error") or "Pi did not start.")

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        if self._exited:
            yield AgentError(f"Pi is not running ({self._exit_message()}). Start the agent again.")
            return
        try:
            await asyncio.wait_for(self._idle.wait(), IDLE_TIMEOUT_S)
        except TimeoutError:
            logger.warning("Pi is still finishing the previous turn")
        events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self._events = events
        self._idle.clear()
        try:
            try:
                response = await self._request({"type": "prompt", "message": text})
            except ConnectionError as exc:
                yield AgentError(f"Pi failed: {exc}")
                return
            if not response.get("success"):
                self._idle.set()
                yield AgentError(f"Pi rejected the message: {response.get('error') or 'no reason given'}")
                return
            if (response.get("data") or {}).get("disposition") == "handled":
                # An extension command consumed it; no run follows.
                self._idle.set()
                yield ReplyDone("")
                return
            reply = ""
            error: str | None = None
            while (record := await events.get()) is not None:
                kind = record.get("type")
                if kind == "message_end":
                    message = record.get("message") or {}
                    if message.get("role") != "assistant":
                        continue
                    texts = [
                        block["text"] for block in message.get("content") or []
                        if isinstance(block, dict) and block.get("type") == "text"
                        and isinstance(block.get("text"), str) and block["text"].strip()
                    ]
                    for block_text in texts:
                        yield TextDelta(block_text)
                    if texts:
                        reply = "\n\n".join(texts)
                    # A later message (an automatic retry) clears an earlier error.
                    error = message.get("errorMessage") if message.get("stopReason") == "error" else None
                elif kind == "tool_execution_start":
                    args = record.get("args")
                    yield ToolActivity(
                        str(record.get("toolName") or "tool"),
                        summarize_tool_input(args) if isinstance(args, dict) else "",
                    )
                elif kind == "agent_settled":
                    if record.get("aborted"):
                        yield AgentError("The turn was interrupted.")
                    elif error:
                        yield AgentError(_readable_error(str(error)))
                    else:
                        yield ReplyDone(reply)
                    return
            # Every turn must still end with ReplyDone or AgentError.
            yield AgentError("Pi stopped before finishing the reply.")
        finally:
            if self._events is events:
                self._events = None

    async def interrupt(self) -> None:
        if self._exited:
            return
        # An unanswered confirm would keep the tool, and so the abort, waiting.
        await self._withdraw_dialogs()
        try:
            # Pi answers once it is idle; agent_settled already ends the turn.
            await self._rpc.send({"type": "abort"})
        except Exception as exc:
            logger.warning("Could not ask Pi to abort: %s", exc)

    async def close(self) -> None:
        await self._withdraw_dialogs()
        try:
            await self._rpc.close()
        finally:
            if self._reader is not None:
                self._reader.cancel()
                await asyncio.gather(self._reader, return_exceptions=True)

    # ------------------------------------------------------------------ #
    # Reading Pi's output                                                 #
    # ------------------------------------------------------------------ #

    async def _read_loop(self) -> None:
        try:
            while (record := await self._rpc.receive()) is not None:
                self._dispatch(record)
        except Exception as exc:
            logger.warning("Reading from Pi failed: %s", exc)
        finally:
            self._exited = True
            for future in self._waiting.values():
                if not future.done():
                    future.set_exception(ConnectionError(self._exit_message()))
            if self._events is not None:
                self._events.put_nowait(None)
            self._idle.set()

    def _dispatch(self, record: dict[str, Any]) -> None:
        kind = record.get("type")
        if kind == "response":
            future = self._waiting.get(record.get("id"))  # type: ignore[arg-type]
            if future is not None and not future.done():
                future.set_result(record)
            return
        if kind == "extension_ui_request":
            self._handle_dialog(record)
            return
        if kind == "tool_execution_start":
            self._last_tool = str(record.get("toolName") or "")
        if self._events is not None:
            self._events.put_nowait(record)
        if kind == "agent_settled":
            self._idle.set()

    async def _request(self, command: dict[str, Any]) -> dict[str, Any]:
        if self._exited:
            raise ConnectionError(self._exit_message())
        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._waiting[request_id] = future
        try:
            await self._rpc.send({"id": request_id, **command})
            return await future
        except OSError as exc:
            raise ConnectionError(f"Pi is not accepting input: {exc}") from exc
        finally:
            self._waiting.pop(request_id, None)

    def _exit_message(self) -> str:
        lines = [line.strip() for line in self._rpc.stderr_tail().splitlines() if line.strip()]
        return lines[-1] if lines else "Pi exited."

    # ------------------------------------------------------------------ #
    # Extension dialogs                                                   #
    # ------------------------------------------------------------------ #

    def _handle_dialog(self, record: dict[str, Any]) -> None:
        request_id = record.get("id")
        if not isinstance(request_id, str):
            return
        method = record.get("method")
        if method == "confirm":
            task = asyncio.create_task(self._answer_confirm(request_id, record))
            self._dialogs[request_id] = task
            task.add_done_callback(lambda _: self._dialogs.pop(request_id, None))
        elif method in _DIALOGS_WITHOUT_VOICE:
            # Socra has no spoken answer for choices or free text: Pi gets "cancelled".
            logger.info("Cancelled a Pi %s dialog: %s", method, record.get("title"))
            task = asyncio.create_task(self._send_quietly(
                {"type": "extension_ui_response", "id": request_id, "cancelled": True}
            ))
            self._background.add(task)
            task.add_done_callback(self._background.discard)
        # notify, setStatus, setWidget, setTitle and set_editor_text need no answer.

    async def _answer_confirm(self, request_id: str, record: dict[str, Any]) -> None:
        request = PermissionRequest(
            request_id=request_id,
            tool=self._last_tool or "pi",
            title=str(record.get("title") or "Pi asks for confirmation"),
            detail=str(record.get("message") or ""),
        )
        try:
            allowed = await self._decide(request)
        except asyncio.CancelledError:
            await self._send_quietly(
                {"type": "extension_ui_response", "id": request_id, "cancelled": True}
            )
            raise
        except Exception as exc:
            # No answer is a denial, never a silent approval.
            logger.error("Permission decision failed for %s: %s", request.tool, exc)
            allowed = False
        await self._send_quietly(
            {"type": "extension_ui_response", "id": request_id, "confirmed": allowed is True}
        )

    async def _withdraw_dialogs(self) -> None:
        tasks = list(self._dialogs.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_quietly(self, record: dict[str, Any]) -> None:
        try:
            await self._rpc.send(record)
        except Exception as exc:
            logger.warning("Could not answer a Pi dialog: %s", exc)


class PiBackend:
    id = "pi"
    label = "Pi"
    # Mode switching needs Socra tools and instructions Pi does not get yet.
    supports_modes = False

    def __init__(
        self,
        *,
        rpc_starter: RpcStarter = SubprocessRpc.start,
        cli_path: str | None = None,
        cache_path: Path = CACHE_PATH,
    ) -> None:
        self._start_rpc = rpc_starter
        self._cli_path = cli_path if cli_path is not None else find_cli()
        self._cache_path = cache_path
        # Models of logged-in providers, in Pi's order: no provider is preferred.
        self._fast: list[ModelOption] = []
        self._full: list[ModelOption] | None = self._read_cache()
        self.model_refresh: asyncio.Task[None] | None = None

    def models(self) -> list[ModelOption]:
        return list(self._full if self._full is not None else self._fast)

    async def check(self) -> BackendStatus:
        if not self._cli_path:
            return BackendStatus("unreachable", "Pi CLI not found.")
        try:
            self._fast = await asyncio.wait_for(
                self._discover(self._cli_path, FAST_DISCOVERY_FLAGS), DISCOVERY_TIMEOUT_S
            )
        except Exception as exc:
            logger.warning("Pi model discovery failed: %s", exc)
            return BackendStatus("unreachable", "Could not run Pi to list its models.")
        if self.model_refresh is None:
            # Once per server run, list extension providers too, for the next page load.
            self.model_refresh = asyncio.create_task(
                self._refresh_full(self._cli_path), name="pi-model-refresh"
            )
        if not self.models():
            return BackendStatus(
                "not_configured", "Pi has no logged-in provider. Run pi and use /login."
            )
        return BackendStatus("ready")

    async def open(
        self, model: str, cwd: Path, decide_permission: PermissionDecider
    ) -> PiConversation:
        provider, model_id = _split_model(model)
        if not self._cli_path:
            raise RuntimeError("Pi CLI not found.")
        # Always explicit: Pi's own default provider is never used implicitly.
        rpc = await self._start_rpc(
            [self._cli_path, "--mode", "rpc", "--provider", provider, "--model", model_id], cwd
        )
        conversation = PiConversation(rpc, decide_permission)
        try:
            await conversation.start()
        except BaseException:
            await conversation.close()
            raise
        return conversation

    async def _refresh_full(self, cli_path: str) -> None:
        try:
            models = await asyncio.wait_for(
                self._discover(cli_path, DISCOVERY_FLAGS), FULL_DISCOVERY_TIMEOUT_S
            )
        except Exception as exc:
            logger.warning("Pi model discovery with extensions failed: %s", exc)
            return
        self._full = models
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps([{"id": m.id, "label": m.label} for m in models]), encoding="utf-8"
            )
        except OSError as exc:
            logger.warning("Could not save the Pi model list: %s", exc)

    async def _discover(self, cli_path: str, flags: tuple[str, ...]) -> list[ModelOption]:
        rpc = await self._start_rpc(
            [cli_path, "--mode", "rpc", *flags], Path(tempfile.gettempdir())
        )
        try:
            await rpc.send({"id": "models", "type": "get_available_models"})
            while True:
                record = await rpc.receive()
                if record is None:
                    raise RuntimeError(f"Pi exited: {rpc.stderr_tail()}")
                if record.get("type") == "response" and record.get("id") == "models":
                    break
            if not record.get("success"):
                raise RuntimeError(str(record.get("error")))
        finally:
            await rpc.close()
        models = (record.get("data") or {}).get("models") or []
        return [option for option in map(_model_option, models) if option is not None]

    def _read_cache(self) -> list[ModelOption] | None:
        try:
            entries = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return [ModelOption(str(e["id"]), str(e["label"])) for e in entries]
        except (OSError, ValueError, TypeError, KeyError):
            return None
