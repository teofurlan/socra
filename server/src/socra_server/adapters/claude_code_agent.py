"""Claude Code adapter for the AgentBackend port, over the Claude Agent SDK.

Claude Code's own settings (user, project and local) still decide which tool
calls are allowed or denied; only calls its rules mark as "ask" reach the
PermissionDecider, which lets the page show Allow / Deny.
"""
from __future__ import annotations

import asyncio
import json
import logging
import platform
import shutil
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import claude_agent_sdk
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
)

from socra_server.adapters.tool_summary import summarize_tool_input as _summarize, tool_path
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

STATUS_TIMEOUT_S = 15.0
DENIED_MESSAGE = "The user denied this action in Socra."

ClientFactory = Callable[[ClaudeAgentOptions], Any]
StatusRunner = Callable[[str], Awaitable[str]]


def find_cli() -> str | None:
    """Prefer the CLI bundled with the SDK, then one on PATH."""
    name = "claude.exe" if platform.system() == "Windows" else "claude"
    bundled = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    if bundled.is_file():
        return str(bundled)
    return shutil.which("claude")


async def run_auth_status(cli_path: str) -> str:
    """Return the JSON printed by ``claude auth status --json``."""
    process = await asyncio.create_subprocess_exec(
        cli_path, "auth", "status", "--json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=STATUS_TIMEOUT_S)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise
    return stdout.decode("utf-8", errors="replace")


class ClaudeCodeConversation:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def send(self, text: str) -> AsyncIterator[AgentEvent]:
        last_text = ""
        try:
            await self._client.query(text)
            async for message in self._client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock) and block.text:
                            last_text = block.text
                            yield TextDelta(block.text)
                        elif isinstance(block, ToolUseBlock):
                            yield ToolActivity(block.name, _summarize(block.input), tool_path(block.input))
                elif isinstance(message, ResultMessage):
                    if message.is_error:
                        detail = "; ".join(message.errors or []) or message.result
                        yield AgentError(detail or f"Claude Code failed ({message.subtype})")
                    else:
                        yield ReplyDone(message.result or last_text)
                    return
        except Exception as exc:
            logger.error("Claude Code turn failed: %s", exc)
            yield AgentError(f"Claude Code failed: {exc}")
            return
        # The SDK stream can end silently when the CLI's output closes; every
        # turn must still end with ReplyDone or AgentError.
        yield AgentError("Claude Code stopped before finishing the reply.")

    async def interrupt(self) -> None:
        await self._client.interrupt()

    async def close(self) -> None:
        await self._client.disconnect()


class ClaudeCodeBackend:
    id = "claude-code"
    label = "Claude Code"
    _MODELS = (
        ModelOption("sonnet", "Sonnet"),
        ModelOption("opus", "Opus"),
        ModelOption("haiku", "Haiku"),
    )

    def __init__(
        self,
        *,
        client_factory: ClientFactory = lambda options: ClaudeSDKClient(options=options),
        status_runner: StatusRunner = run_auth_status,
        cli_path: str | None = None,
    ) -> None:
        self._client_factory = client_factory
        self._status_runner = status_runner
        self._cli_path = cli_path if cli_path is not None else find_cli()

    def models(self) -> list[ModelOption]:
        return list(self._MODELS)

    async def check(self) -> BackendStatus:
        if not self._cli_path:
            return BackendStatus("unreachable", "Claude Code CLI not found.")
        try:
            output = await self._status_runner(self._cli_path)
            # Read only the login flag: account details never leave the server.
            logged_in = json.loads(output).get("loggedIn") is True
        except Exception as exc:
            logger.warning("claude auth status failed: %s", exc)
            return BackendStatus("unreachable", "Could not run Claude Code to check its login.")
        if not logged_in:
            return BackendStatus(
                "not_configured", "Claude Code is not logged in. Run: claude auth login"
            )
        return BackendStatus("ready")

    async def open(
        self, model: str, cwd: Path, decide_permission: PermissionDecider
    ) -> ClaudeCodeConversation:
        async def can_use_tool(
            tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
        ) -> PermissionResultAllow | PermissionResultDeny:
            request = PermissionRequest(
                request_id=context.tool_use_id or uuid.uuid4().hex,
                tool=tool_name,
                title=context.title or context.display_name or f"Use {tool_name}",
                detail=context.description or _summarize(tool_input),
            )
            try:
                allowed = await decide_permission(request)
            except Exception as exc:
                # No answer is a denial, never a silent approval.
                logger.error("Permission decision failed for %s: %s", tool_name, exc)
                allowed = False
            if allowed is True:
                return PermissionResultAllow()
            return PermissionResultDeny(message=DENIED_MESSAGE)

        options = ClaudeAgentOptions(
            model=model,
            cwd=str(cwd),
            cli_path=self._cli_path,
            can_use_tool=can_use_tool,
            # Unset would make the SDK pass an empty system prompt.
            system_prompt={"type": "preset", "preset": "claude_code"},
        )
        client = self._client_factory(options)
        await client.connect()
        return ClaudeCodeConversation(client)
