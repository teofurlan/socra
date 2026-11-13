"""Tests for the Claude Code agent adapter, with a fake SDK client (no CLI, no network)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    CLIConnectionError,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    TextBlock,
    ToolPermissionContext,
    ToolUseBlock,
)

from socra_server.adapters.claude_code_agent import ClaudeCodeBackend, ClaudeCodeConversation
from socra_server.domain.agent import (
    AgentError,
    BackendStatus,
    CommandOption,
    PermissionRequest,
    ReplyDone,
    TextDelta,
    ToolActivity,
)
from socra_server.ports import AgentBackend, AgentConversation


def _result(
    text: str | None = "Done.",
    *,
    is_error: bool = False,
    errors=None,
    terminal_reason: str | None = None,
) -> ResultMessage:
    return ResultMessage(
        subtype="error_during_execution" if is_error else "success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=is_error,
        num_turns=1,
        session_id="session-1",
        result=text,
        errors=errors,
        terminal_reason=terminal_reason,
    )


class FakeClient:
    """Stands in for ClaudeSDKClient; replays scripted messages for each query."""

    instances: list["FakeClient"] = []

    def __init__(self, options=None, script=None, fail_with: Exception | None = None,
                 info=None, info_error: Exception | None = None):
        self.options = options
        self.script = list(script or [])
        self.fail_with = fail_with
        self.info = info
        self.info_error = info_error
        self.queries: list[str] = []
        self.connected = False
        self.interrupted = False
        self.disconnected = False
        FakeClient.instances.append(self)

    async def connect(self):
        self.connected = True

    async def query(self, prompt: str):
        if self.fail_with is not None:
            raise self.fail_with
        self.queries.append(prompt)

    async def receive_response(self):
        for message in self.script:
            yield message

    async def interrupt(self):
        self.interrupted = True

    async def get_server_info(self):
        if self.info_error is not None:
            raise self.info_error
        return self.info

    async def disconnect(self):
        self.disconnected = True


def _backend(script=None, fail_with=None, status_output=None, status_error=None, info=None,
             info_error=None):
    def factory(options):
        return FakeClient(options=options, script=script, fail_with=fail_with, info=info,
                          info_error=info_error)

    async def run_status(cli_path: str) -> str:
        if status_error is not None:
            raise status_error
        return status_output

    return ClaudeCodeBackend(
        client_factory=factory, status_runner=run_status, cli_path="claude-test.exe"
    )


async def _never_asked(request: PermissionRequest) -> bool:
    raise AssertionError("decider should not be called")


async def _collect(conversation, text="hello"):
    return [event async for event in conversation.send(text)]


def test_backend_satisfies_port_and_offers_claude_models():
    backend = _backend()

    assert isinstance(backend, AgentBackend)
    assert backend.id == "claude-code"
    assert [m.id for m in backend.models()] == ["sonnet", "opus", "haiku"]


async def test_open_connects_with_model_cwd_cli_and_permission_callback(tmp_path):
    backend = _backend()

    conversation = await backend.open("opus", tmp_path, _never_asked)

    client = FakeClient.instances[-1]
    assert isinstance(conversation, AgentConversation)
    assert client.connected
    assert client.options.model == "opus"
    assert Path(client.options.cwd) == tmp_path
    assert client.options.cli_path == "claude-test.exe"
    assert client.options.can_use_tool is not None
    # The user's own defaultMode decides; Socra never overrides it.
    assert client.options.permission_mode is None
    # Keep Claude Code's own system prompt (unset would send an empty one).
    assert client.options.system_prompt == {"type": "preset", "preset": "claude_code"}


async def test_send_streams_text_tools_and_final_reply(tmp_path):
    script = [
        AssistantMessage(
            content=[
                TextBlock(text="Let me look."),
                ToolUseBlock(id="t1", name="Read", input={"file_path": "src/app.py"}),
            ],
            model="opus",
        ),
        AssistantMessage(content=[TextBlock(text="It defines ExamApp.")], model="opus"),
        _result("It defines ExamApp."),
    ]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation, "what is in app.py?")

    assert FakeClient.instances[-1].queries == ["what is in app.py?"]
    assert events == [
        TextDelta("Let me look."),
        ToolActivity("Read", "src/app.py", "src/app.py"),
        TextDelta("It defines ExamApp."),
        ReplyDone("It defines ExamApp."),
    ]


async def test_final_reply_falls_back_to_last_text_when_result_is_empty(tmp_path):
    script = [AssistantMessage(content=[TextBlock(text="Hi there.")], model="opus"), _result(None)]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events[-1] == ReplyDone("Hi there.")


async def test_failed_turn_yields_agent_error(tmp_path):
    script = [_result(None, is_error=True, errors=["Rate limited"])]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events == [AgentError("Rate limited")]


async def test_interrupted_turn_yields_interrupted_error_when_conversation_interrupted(tmp_path):
    script = [
        AssistantMessage(content=[TextBlock(text="Thinking...")], model="opus"),
        _result(None, is_error=True, errors=["[ede_diagnostic … stop_reason=null]"]),
    ]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)
    await conversation.interrupt()

    events = await _collect(conversation)

    assert events == [TextDelta("Thinking..."), AgentError("The turn was interrupted.")]


async def test_interrupted_turn_during_streaming_yields_interrupted_error(tmp_path):
    client = FakeClient()

    async def stream_and_interrupt():
        yield AssistantMessage(content=[TextBlock(text="Thinking...")], model="opus")
        await conversation.interrupt()
        yield _result(None, is_error=True, errors=["some generic error"])

    client.receive_response = stream_and_interrupt
    conversation = ClaudeCodeConversation(client)

    events = [event async for event in conversation.send("hello")]

    assert events == [TextDelta("Thinking..."), AgentError("The turn was interrupted.")]


async def test_interrupted_turn_recognized_from_terminal_reason(tmp_path):
    script = [
        _result(None, is_error=True, errors=["some error"], terminal_reason="aborted_streaming")
    ]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events == [AgentError("The turn was interrupted.")]


@pytest.mark.parametrize(
    "diag",
    [
        "[ede_diagnostic … stop_reason=null]",
        "prompt_check failed: prompt was checked",
    ],
)
async def test_raw_sdk_interruption_diagnostics_yield_clean_interrupted_error(tmp_path, diag):
    script = [_result(None, is_error=True, errors=[diag])]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events == [AgentError("The turn was interrupted.")]


async def test_interrupted_turn_with_exception_yields_interrupted_error(tmp_path):
    client = FakeClient()

    async def stream_with_abort():
        yield AssistantMessage(content=[TextBlock(text="Thinking...")], model="opus")
        await conversation.interrupt()
        raise CLIConnectionError("Stream closed")

    client.receive_response = stream_with_abort
    conversation = ClaudeCodeConversation(client)

    events = [event async for event in conversation.send("hello")]

    assert events == [TextDelta("Thinking..."), AgentError("The turn was interrupted.")]


async def test_client_failure_yields_agent_error_instead_of_raising(tmp_path):
    backend = _backend(fail_with=CLIConnectionError("CLI exited"))
    conversation = await backend.open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert len(events) == 1
    assert isinstance(events[0], AgentError)
    assert "CLI exited" in events[0].message


async def test_stream_ending_without_result_still_ends_the_turn(tmp_path):
    script = [AssistantMessage(content=[TextBlock(text="partial")], model="opus")]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events[0] == TextDelta("partial")
    assert isinstance(events[-1], AgentError)
    assert len(events) == 2


async def test_interrupt_and_close_reach_the_client(tmp_path):
    conversation = await _backend().open("opus", tmp_path, _never_asked)
    client = FakeClient.instances[-1]

    await conversation.interrupt()
    await conversation.close()

    assert client.interrupted
    assert client.disconnected


async def _ask_permission(tmp_path, decider):
    await _backend().open("opus", tmp_path, decider)
    can_use_tool = FakeClient.instances[-1].options.can_use_tool
    context = ToolPermissionContext(
        tool_use_id="tool-7",
        title="Claude wants to run git status",
        description="Shows the working tree status",
    )
    return await can_use_tool("Bash", {"command": "git status"}, context)


async def test_permission_request_is_mapped_and_allowed(tmp_path):
    seen: list[PermissionRequest] = []

    async def allow(request: PermissionRequest) -> bool:
        seen.append(request)
        return True

    result = await _ask_permission(tmp_path, allow)

    assert isinstance(result, PermissionResultAllow)
    assert seen == [
        PermissionRequest(
            request_id="tool-7",
            tool="Bash",
            title="Claude wants to run git status",
            detail="Shows the working tree status",
        )
    ]


async def test_permission_denied_by_user(tmp_path):
    async def deny(request: PermissionRequest) -> bool:
        return False

    result = await _ask_permission(tmp_path, deny)

    assert isinstance(result, PermissionResultDeny)


async def test_permission_allows_only_an_explicit_true(tmp_path):
    async def vague(request: PermissionRequest):
        return "no"

    result = await _ask_permission(tmp_path, vague)

    assert isinstance(result, PermissionResultDeny)


async def test_permission_denied_when_decider_fails(tmp_path):
    async def broken(request: PermissionRequest) -> bool:
        raise RuntimeError("page disconnected")

    result = await _ask_permission(tmp_path, broken)

    assert isinstance(result, PermissionResultDeny)


@pytest.mark.parametrize(
    ("output", "error", "expected_state"),
    [
        (json.dumps({"loggedIn": True, "email": "x@example.com"}), None, "ready"),
        (json.dumps({"loggedIn": False}), None, "not_configured"),
        (None, FileNotFoundError("claude-test.exe"), "unreachable"),
        ("not json", None, "unreachable"),
    ],
)
async def test_check_reports_login_state(output, error, expected_state):
    status = await _backend(status_output=output, status_error=error).check()

    assert status.state == expected_state
    assert "example.com" not in status.message
    if expected_state != "ready":
        assert status.message


async def test_check_ready_has_no_message():
    status = await _backend(status_output=json.dumps({"loggedIn": True})).check()

    assert status == BackendStatus("ready")


# --------------------------------------------------------------------------- #
# Modes: instructions and Socra tools                                          #
# --------------------------------------------------------------------------- #

class _Toolbox:
    def __init__(self):
        self.calls = []

    async def switch_mode(self, target):
        self.calls.append(target)
        return "asked the user"

    async def record_exam_result(self, question, verdict, note):
        return "recorded"

    async def search_transcript(self, query, limit):
        return []


def test_claude_code_supports_modes():
    assert _backend().supports_modes is True


async def test_an_agent_session_pre_approves_only_the_switch_and_search_tools(tmp_path):  # S2
    from socra_server.domain.modes import get_mode

    await _backend().open("opus", tmp_path, _never_asked, mode=get_mode("agent"), toolbox=_Toolbox())

    options = FakeClient.instances[-1].options
    assert sorted(options.allowed_tools) == ["mcp__socra__search_transcript", "mcp__socra__switch_mode"]
    assert options.system_prompt["append"] == get_mode("agent").instructions


async def test_open_in_a_mode_appends_its_instructions_and_exposes_socra_tools(tmp_path):
    from socra_server.domain.modes import get_mode

    toolbox = _Toolbox()
    await _backend().open("opus", tmp_path, _never_asked, mode=get_mode("exam"), toolbox=toolbox)

    options = FakeClient.instances[-1].options
    assert options.system_prompt == {
        "type": "preset", "preset": "claude_code", "append": get_mode("exam").instructions,
    }
    assert set(options.mcp_servers) == {"socra"}
    assert options.mcp_servers["socra"]["type"] == "sdk"
    # Socra's own tools are pre-approved: they must not raise an Allow / Deny prompt.
    assert sorted(options.allowed_tools) == [
        "mcp__socra__clear_scene",
        "mcp__socra__point_at",
        "mcp__socra__present",
        "mcp__socra__record_exam_result",
        "mcp__socra__replay_step",
        "mcp__socra__scene_guide",
        "mcp__socra__search_transcript",
        "mcp__socra__show_result",
        "mcp__socra__switch_mode",
    ]


async def test_socra_tool_calls_reach_the_toolbox_and_return_text(tmp_path):
    from socra_server.adapters.claude_code_agent import sdk_tools
    from socra_server.domain.modes import get_mode

    toolbox = _Toolbox()
    tools = {t.name: t for t in sdk_tools(get_mode("exam"), toolbox)}

    result = await tools["switch_mode"].handler({"mode": "mentor"})

    assert toolbox.calls == ["mentor"]
    assert result == {"content": [{"type": "text", "text": "asked the user"}]}


async def test_a_failing_socra_tool_reports_an_error_result(tmp_path):
    from socra_server.adapters.claude_code_agent import sdk_tools
    from socra_server.domain.modes import get_mode

    class Broken(_Toolbox):
        async def switch_mode(self, target):
            raise RuntimeError("boom")

    tools = {t.name: t for t in sdk_tools(get_mode("mentor"), Broken())}

    result = await tools["switch_mode"].handler({"mode": "exam"})

    assert result["is_error"] is True
    assert "boom" in result["content"][0]["text"]


async def test_a_mode_without_a_toolbox_only_appends_instructions(tmp_path):
    from socra_server.domain.modes import get_mode

    await _backend().open("opus", tmp_path, _never_asked, mode=get_mode("mentor"))

    options = FakeClient.instances[-1].options
    assert options.system_prompt["append"] == get_mode("mentor").instructions
    assert not options.mcp_servers
    assert not options.allowed_tools


def _text_delta_event(text: str, parent_tool_use_id: str | None = None):
    from claude_agent_sdk import StreamEvent

    return StreamEvent(
        uuid="u1",
        session_id="session-1",
        event={"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": text}},
        parent_tool_use_id=parent_tool_use_id,
    )


async def test_open_asks_the_sdk_for_partial_messages(tmp_path):  # S3
    await _backend().open("opus", tmp_path, _never_asked)

    assert FakeClient.instances[-1].options.include_partial_messages is True


async def test_partial_text_streams_as_chunks_before_the_whole_block(tmp_path):  # S3
    from socra_server.domain.agent import TextChunk

    script = [
        _text_delta_event("Hola. "),
        _text_delta_event("Ya miro."),
        AssistantMessage(content=[TextBlock(text="Hola. Ya miro.")], model="opus"),
        _result("Hola. Ya miro."),
    ]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events == [
        TextChunk("Hola. "),
        TextChunk("Ya miro."),
        TextDelta("Hola. Ya miro.", spoken=True),
        ReplyDone("Hola. Ya miro."),
    ]


async def test_subagent_and_non_text_stream_events_are_not_chunks(tmp_path):  # S3
    from claude_agent_sdk import StreamEvent

    script = [
        _text_delta_event("inner", parent_tool_use_id="t9"),
        StreamEvent(uuid="u2", session_id="s", event={"type": "content_block_delta", "delta": {"type": "input_json_delta", "partial_json": "{"}}),
        StreamEvent(uuid="u3", session_id="s", event={"type": "message_start"}),
        AssistantMessage(content=[TextBlock(text="Done.")], model="opus"),
        _result("Done."),
    ]
    conversation = await _backend(script=script).open("opus", tmp_path, _never_asked)

    events = await _collect(conversation)

    assert events == [TextDelta("Done."), ReplyDone("Done.")]


async def test_commands_are_the_ones_the_session_reports_with_their_hints(tmp_path):
    info = {"commands": [
        {"name": "tdd", "description": "Test-driven development", "argumentHint": "<feature>"},
        {"name": "context", "description": "Show context usage"},
        {"description": "no name"},
    ], "other": 1}
    conversation = await _backend(info=info).open("opus", tmp_path, _never_asked)

    assert await conversation.commands() == [
        CommandOption("tdd", "Test-driven development", "<feature>"),
        CommandOption("context", "Show context usage", ""),
    ]


@pytest.mark.parametrize("info", [None, {}, {"commands": None}, "nope"])
async def test_commands_are_empty_when_the_session_reports_none(tmp_path, info):
    conversation = await _backend(info=info).open("opus", tmp_path, _never_asked)

    assert await conversation.commands() == []


async def test_commands_failure_is_raised_for_the_caller_to_handle(tmp_path):
    conversation = await _backend(info_error=RuntimeError("no info")).open(
        "opus", tmp_path, _never_asked
    )

    with pytest.raises(RuntimeError):
        await conversation.commands()
