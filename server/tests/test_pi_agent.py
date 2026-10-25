"""Tests for the Pi agent adapter, with a fake `pi --mode rpc` process (no Pi, no network)."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from socra_server.adapters.pi_agent import PiBackend, SubprocessRpc
from socra_server.domain.agent import (
    AgentError,
    BackendStatus,
    ModelOption,
    PermissionRequest,
    ReplyDone,
    TextDelta,
    ToolActivity,
)
from socra_server.ports import AgentBackend, AgentConversation

GPT = {"provider": "openai-codex", "id": "gpt-6.1-sol", "name": "GPT-6.1 Sol"}
GEMINI = {"provider": "google", "id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash Lite"}
GROQ = {"provider": "groq", "id": "openai/gpt-oss-120b", "name": "GPT OSS 120B"}
ANTIGRAVITY = {"provider": "antigravity", "id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"}


# --------------------------------------------------------------------------- #
# Records as Pi 1.3.0 prints them (trimmed from the real probes in the doc)   #
# --------------------------------------------------------------------------- #

def _assistant(*blocks, stop="stop", error=None):
    message = {"role": "assistant", "content": list(blocks), "stopReason": stop}
    if error is not None:
        message["errorMessage"] = error
    return {"type": "message_end", "message": message}


def _text(text):
    return {"type": "text", "text": text}


def _tool_call(name, args):
    return {"type": "toolCall", "id": "call_1", "name": name, "arguments": args}


def _tool_start(name, args):
    return {"type": "tool_execution_start", "toolCallId": "call_1", "toolName": name, "args": args}


def _settled(aborted=False):
    return {"type": "agent_settled", "aborted": aborted}


READ_NOTE_TURN = [
    {"type": "agent_start"},
    {"type": "message_end", "message": {"role": "user", "content": [_text("read note.txt")]}},
    {"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "he"}},
    _assistant(_tool_call("read", {"path": "note.txt"}), _text(""), stop="toolUse"),
    _tool_start("read", {"limit": 10, "offset": 1, "path": "note.txt"}),
    {"type": "tool_execution_end", "toolCallId": "call_1", "toolName": "read", "isError": False},
    {"type": "message_end", "message": {"role": "toolResult", "content": [_text("hello\n")]}},
    _assistant(_text("hello")),
    {"type": "agent_end", "messages": []},
    _settled(),
]


class FakePi:
    """Stands in for a `pi --mode rpc` process: answers commands and replays scripted turns."""

    instances: list["FakePi"] = []

    def __init__(
        self,
        args,
        cwd,
        *,
        models=(GPT, GEMINI),
        extension_models=(ANTIGRAVITY,),
        default=GPT,
        turns=(),
        full_discovery_fails=False,
        prompt_response=None,
        exit_on_start=False,
        stderr="",
    ):
        self.args = list(args)
        self.cwd = cwd
        # Providers that extensions add are listed only when extensions load.
        with_extensions = "--no-extensions" not in self.args
        self.models = [dict(m) for m in (*models, *(extension_models if with_extensions else ()))]
        self.default = default
        self.turns = [list(turn) for turn in turns]
        self.prompt_response = prompt_response
        self.stderr = stderr
        self.sent: list[dict] = []
        self.closed = False
        self._out: asyncio.Queue = asyncio.Queue()
        if exit_on_start or (full_discovery_fails and with_extensions):
            self._out.put_nowait(None)
        FakePi.instances.append(self)

    # PiRpc
    async def send(self, record: dict) -> None:
        self.sent.append(record)
        kind = record["type"]
        if kind == "get_state":
            self._respond(record, {"model": self.default} if self.default else {})
        elif kind == "get_available_models":
            self._respond(record, {"models": self.models})
        elif kind == "prompt":
            if self.prompt_response is not None:
                self._out.put_nowait({"id": record.get("id"), "type": "response", **self.prompt_response})
                return
            self._respond(record, {"disposition": "started"})
            for event in self.turns.pop(0) if self.turns else []:
                self.emit(event)
        elif kind == "abort":
            self.emit(_assistant(stop="error", error="This operation was aborted"))
            self.emit(_settled(aborted=True))
            self._respond(record, None)

    async def receive(self):
        return await self._out.get()

    async def close(self) -> None:
        self.closed = True
        self._out.put_nowait(None)

    def stderr_tail(self) -> str:
        return self.stderr

    # Test helpers
    def emit(self, record) -> None:
        self._out.put_nowait(record)

    def exit(self) -> None:
        self._out.put_nowait(None)

    def commands(self, kind: str) -> list[dict]:
        return [r for r in self.sent if r["type"] == kind]

    def _respond(self, record, data) -> None:
        response = {"id": record.get("id"), "type": "response", "command": record["type"], "success": True}
        if data is not None:
            response["data"] = data
        self._out.put_nowait(response)


def _backend(tmp_path, *, cached=None, start_error=None, **fake_options):
    async def start(args, cwd):
        if start_error is not None:
            raise start_error
        return FakePi(args, cwd, **fake_options)

    cache_path = tmp_path / "cache" / "pi-models.json"
    if cached is not None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cached), encoding="utf-8")
    return PiBackend(rpc_starter=start, cli_path="pi-test.cmd", cache_path=cache_path)


async def _never_asked(request: PermissionRequest) -> bool:
    raise AssertionError("decider should not be called")


async def _collect(conversation, text="hello"):
    return [event async for event in conversation.send(text)]


async def _until(condition, timeout=2.0):
    async def poll():
        while not condition():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout)


# --------------------------------------------------------------------------- #
# Backend: identity, models, check                                            #
# --------------------------------------------------------------------------- #

def test_backend_satisfies_port_and_has_no_models_before_any_check(tmp_path):
    backend = _backend(tmp_path)

    assert isinstance(backend, AgentBackend)
    assert backend.id == "pi"
    assert backend.label == "Pi"
    # Mode switching needs Socra tools and instructions Pi does not get yet.
    assert backend.supports_modes is False
    # No model is offered from Pi's settings: its default provider is never preferred.
    assert backend.models() == []


def test_the_list_saved_by_an_earlier_run_is_offered_before_any_check(tmp_path):
    backend = _backend(tmp_path, cached=[{"id": "antigravity/gemini-3.8-flash", "label": "G"}])

    assert backend.models() == [ModelOption("antigravity/gemini-3.8-flash", "G")]


async def test_check_lists_logged_in_models_in_pis_order_without_preferring_the_default(tmp_path):
    backend = _backend(tmp_path, models=(GEMINI, GPT, GROQ), default=GPT)

    status = await backend.check()

    assert status == BackendStatus("ready")
    assert backend.models() == [
        ModelOption("google/gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (google)"),
        ModelOption("openai-codex/gpt-6.1-sol", "GPT-6.1 Sol (openai-codex)"),
        ModelOption("groq/openai/gpt-oss-120b", "GPT OSS 120B (groq)"),
    ]
    probe = FakePi.instances[0]
    # The first listing skips extensions so the selector stays fast.
    assert probe.args[:3] == ["pi-test.cmd", "--mode", "rpc"]
    for flag in ("--no-session", "--no-extensions", "--no-mcp", "--offline"):
        assert flag in probe.args
    assert probe.closed


async def test_extension_providers_are_listed_after_the_background_refresh_and_saved(tmp_path):
    backend = _backend(tmp_path, models=(GEMINI,), extension_models=(ANTIGRAVITY,))

    await backend.check()
    await backend.model_refresh

    expected = [
        ModelOption("google/gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite (google)"),
        ModelOption("antigravity/gemini-3.8-flash", "Gemini 3.8 Flash (antigravity)"),
    ]
    assert backend.models() == expected
    full = FakePi.instances[-1]
    assert "--no-extensions" not in full.args
    assert "--no-session" in full.args and full.closed
    # A new server run offers the full list at once.
    assert _backend(tmp_path).models() == expected


async def test_the_background_refresh_runs_once_per_server_run(tmp_path):
    backend = _backend(tmp_path)
    await backend.check()
    refresh = backend.model_refresh

    await backend.check()

    assert backend.model_refresh is refresh


async def test_a_failed_refresh_keeps_the_fast_list(tmp_path):
    backend = _backend(tmp_path, models=(GEMINI,), full_discovery_fails=True)

    await backend.check()
    await backend.model_refresh

    assert [m.id for m in backend.models()] == ["google/gemini-3.5-flash-lite"]
    assert not (tmp_path / "cache" / "pi-models.json").exists()


async def test_check_without_logged_in_providers_is_not_configured(tmp_path):
    status = await _backend(tmp_path, models=(), extension_models=(), default=None).check()

    assert status.state == "not_configured"
    assert "/login" in status.message


@pytest.mark.parametrize(
    ("options", "message_part"),
    [
        ({"start_error": FileNotFoundError("pi-test.cmd")}, "Could not run Pi"),
        ({"exit_on_start": True, "stderr": "boom"}, "Could not run Pi"),
    ],
)
async def test_check_reports_unreachable_when_pi_cannot_run(tmp_path, options, message_part):
    status = await _backend(tmp_path, **options).check()

    assert status.state == "unreachable"
    assert message_part in status.message


async def test_check_without_cli_is_unreachable(tmp_path):
    backend = PiBackend(cli_path="", cache_path=tmp_path / "pi-models.json")

    status = await backend.check()

    assert status == BackendStatus("unreachable", "Pi CLI not found.")


# --------------------------------------------------------------------------- #
# Opening a conversation                                                      #
# --------------------------------------------------------------------------- #

async def test_open_starts_pi_in_rpc_mode_with_provider_model_and_folder(tmp_path):
    backend = _backend(tmp_path)

    conversation = await backend.open("google/gemini-3.5-flash-lite", tmp_path, _never_asked)

    pi = FakePi.instances[-1]
    assert isinstance(conversation, AgentConversation)
    assert pi.args == [
        "pi-test.cmd", "--mode", "rpc",
        "--provider", "google", "--model", "gemini-3.5-flash-lite",
    ]
    assert Path(pi.cwd) == tmp_path
    # open() returns only once Pi has answered, so the first turn is not lost.
    assert pi.commands("get_state")


async def test_open_splits_provider_from_a_model_id_that_has_a_slash(tmp_path):
    backend = _backend(tmp_path, models=(GROQ,), default=GROQ)

    await backend.open("groq/openai/gpt-oss-120b", tmp_path, _never_asked)

    assert FakePi.instances[-1].args[-4:] == ["--provider", "groq", "--model", "openai/gpt-oss-120b"]


async def test_open_fails_with_pis_own_message_when_it_exits(tmp_path):
    stderr = 'Error: Model "google/gone" not found. Use --list-models to see available models.'
    backend = _backend(tmp_path, exit_on_start=True, stderr=stderr)

    with pytest.raises(RuntimeError, match="not found"):
        await backend.open("google/gone", tmp_path, _never_asked)


@pytest.mark.parametrize("model", ["no-provider", 'google/x" & calc', "google/"])
async def test_open_rejects_malformed_model_ids_without_starting_pi(tmp_path, model):
    backend = _backend(tmp_path)
    before = len(FakePi.instances)

    with pytest.raises(ValueError):
        await backend.open(model, tmp_path, _never_asked)

    assert len(FakePi.instances) == before


# --------------------------------------------------------------------------- #
# Turns                                                                       #
# --------------------------------------------------------------------------- #

async def _open(tmp_path, decider=_never_asked, **fake_options):
    conversation = await _backend(tmp_path, **fake_options).open(
        "google/gemini-3.5-flash-lite", tmp_path, decider
    )
    return conversation, FakePi.instances[-1]


async def test_send_streams_tools_text_blocks_and_final_reply(tmp_path):
    conversation, pi = await _open(tmp_path, turns=[READ_NOTE_TURN])

    events = await _collect(conversation, "what is in note.txt?")

    assert [p["message"] for p in pi.commands("prompt")] == ["what is in note.txt?"]
    # Token deltas are not forwarded (the page adds one entry per text);
    # blank text blocks are skipped.
    assert events == [
        ToolActivity("read", "note.txt"),
        TextDelta("hello"),
        ReplyDone("hello"),
    ]


async def test_final_reply_joins_the_text_blocks_of_the_last_message(tmp_path):
    turn = [_assistant(_text("First part."), _text("Second part.")), _settled()]
    conversation, _ = await _open(tmp_path, turns=[turn])

    events = await _collect(conversation)

    assert events == [
        TextDelta("First part."),
        TextDelta("Second part."),
        ReplyDone("First part.\n\nSecond part."),
    ]


async def test_provider_error_yields_a_readable_agent_error(tmp_path):
    nested = json.dumps({"error": {"message": json.dumps({"error": {
        "code": 404,
        "message": "This model models/gemini-2.5-flash-lite is no longer available to new users.",
    }})}})
    turn = [_assistant(stop="error", error=nested), _settled()]
    conversation, _ = await _open(tmp_path, turns=[turn])

    events = await _collect(conversation)

    assert events == [
        AgentError("This model models/gemini-2.5-flash-lite is no longer available to new users.")
    ]


async def test_a_retried_error_followed_by_a_reply_is_not_an_error(tmp_path):
    turn = [
        _assistant(stop="error", error="529 overloaded"),
        {"type": "auto_retry_start", "attempt": 1},
        _assistant(_text("Recovered.")),
        _settled(),
    ]
    conversation, _ = await _open(tmp_path, turns=[turn])

    events = await _collect(conversation)

    assert events[-1] == ReplyDone("Recovered.")


async def test_rejected_prompt_yields_agent_error(tmp_path):
    conversation, _ = await _open(
        tmp_path, prompt_response={"command": "prompt", "success": False, "error": "Agent is busy"}
    )

    events = await _collect(conversation)

    assert len(events) == 1
    assert isinstance(events[0], AgentError)
    assert "Agent is busy" in events[0].message


async def test_prompt_handled_by_an_extension_ends_the_turn_without_a_run(tmp_path):
    conversation, _ = await _open(
        tmp_path,
        prompt_response={"command": "prompt", "success": True, "data": {"disposition": "handled"}},
    )

    events = await _collect(conversation, "/gentle:mode status")

    assert events == [ReplyDone("")]


async def test_pi_exiting_mid_turn_still_ends_the_turn(tmp_path):
    turn = [_assistant(_text("partial"), stop="toolUse")]
    conversation, pi = await _open(tmp_path, turns=[turn])

    async def exit_later():
        await _until(lambda: pi.commands("prompt"))
        await asyncio.sleep(0.01)
        pi.exit()

    exiting = asyncio.create_task(exit_later())
    events = await _collect(conversation)
    await exiting

    assert events[0] == TextDelta("partial")
    assert isinstance(events[-1], AgentError)
    assert len(events) == 2


async def test_send_after_pi_exited_yields_agent_error(tmp_path):
    conversation, pi = await _open(tmp_path)
    pi.exit()
    await asyncio.sleep(0.01)

    events = await _collect(conversation)

    assert len(events) == 1
    assert isinstance(events[0], AgentError)


async def test_interrupt_aborts_the_turn(tmp_path):
    turn = [_assistant(_tool_call("bash", {"command": "sleep 30"}), stop="toolUse"),
            _tool_start("bash", {"command": "sleep 30"})]
    conversation, pi = await _open(tmp_path, turns=[turn])

    async def interrupt_later():
        await _until(lambda: pi.commands("prompt"))
        await asyncio.sleep(0.01)
        await conversation.interrupt()

    interrupting = asyncio.create_task(interrupt_later())
    events = await _collect(conversation)
    await interrupting

    assert pi.commands("abort")
    assert events[0] == ToolActivity("bash", "sleep 30")
    assert events[-1] == AgentError("The turn was interrupted.")


async def test_a_stopped_turn_does_not_leak_events_into_the_next(tmp_path):
    first = [_assistant(_text("one")), _assistant(_text("stale")), _settled()]
    second = [_assistant(_text("two")), _settled()]
    conversation, _ = await _open(tmp_path, turns=[first, second])

    stream = conversation.send("first")
    assert await anext(stream) == TextDelta("one")
    await stream.aclose()
    events = await _collect(conversation, "second")

    assert events == [TextDelta("two"), ReplyDone("two")]


async def test_close_shuts_pi_down(tmp_path):
    conversation, pi = await _open(tmp_path)

    await conversation.close()

    assert pi.closed


# --------------------------------------------------------------------------- #
# Permissions: extension confirm dialogs (gentle-pi's guarded commands)        #
# --------------------------------------------------------------------------- #

CONFIRM = {
    "type": "extension_ui_request",
    "id": "ui-7",
    "method": "confirm",
    "title": "Allow recognized data-loss command?",
    "message": "rm -rf junk",
}


async def _confirm(tmp_path, decider):
    _, pi = await _open(tmp_path, decider)
    pi.emit(_tool_start("bash", {"command": "rm -rf junk"}))
    pi.emit(dict(CONFIRM))
    await _until(lambda: pi.commands("extension_ui_response"))
    return pi.commands("extension_ui_response")


async def test_confirm_dialog_is_mapped_to_the_decider_and_allowed(tmp_path):
    seen: list[PermissionRequest] = []

    async def allow(request: PermissionRequest) -> bool:
        seen.append(request)
        return True

    responses = await _confirm(tmp_path, allow)

    assert seen == [
        PermissionRequest(
            request_id="ui-7",
            tool="bash",
            title="Allow recognized data-loss command?",
            detail="rm -rf junk",
        )
    ]
    assert responses == [{"type": "extension_ui_response", "id": "ui-7", "confirmed": True}]


async def test_confirm_denied_by_user(tmp_path):
    async def deny(request: PermissionRequest) -> bool:
        return False

    responses = await _confirm(tmp_path, deny)

    assert responses == [{"type": "extension_ui_response", "id": "ui-7", "confirmed": False}]


async def test_confirm_allows_only_an_explicit_true(tmp_path):
    async def vague(request: PermissionRequest):
        return "yes"

    responses = await _confirm(tmp_path, vague)

    assert responses[0]["confirmed"] is False


async def test_confirm_denied_when_decider_fails(tmp_path):
    async def broken(request: PermissionRequest) -> bool:
        raise RuntimeError("page disconnected")

    responses = await _confirm(tmp_path, broken)

    assert responses[0]["confirmed"] is False


async def test_other_dialogs_are_cancelled_without_asking(tmp_path):
    _, pi = await _open(tmp_path)

    pi.emit({"type": "extension_ui_request", "id": "ui-1", "method": "select",
             "title": "Pick one", "options": ["a", "b"]})
    pi.emit({"type": "extension_ui_request", "id": "ui-2", "method": "setStatus",
             "statusKey": "gentle:mode", "statusText": "Permissions: NORMAL"})
    await _until(lambda: pi.commands("extension_ui_response"))
    await asyncio.sleep(0.01)

    assert pi.commands("extension_ui_response") == [
        {"type": "extension_ui_response", "id": "ui-1", "cancelled": True}
    ]


async def test_interrupt_withdraws_an_unanswered_confirm(tmp_path):
    asked = asyncio.Event()
    cancelled = asyncio.Event()

    async def waits_forever(request: PermissionRequest) -> bool:
        asked.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return True

    conversation, pi = await _open(tmp_path, waits_forever)
    pi.emit(dict(CONFIRM))
    await asyncio.wait_for(asked.wait(), 2)

    await conversation.interrupt()
    await _until(lambda: pi.commands("extension_ui_response"))

    assert cancelled.is_set()
    assert pi.commands("extension_ui_response") == [
        {"type": "extension_ui_response", "id": "ui-7", "cancelled": True}
    ]


# --------------------------------------------------------------------------- #
# Transport: a real child process speaking JSONL                               #
# --------------------------------------------------------------------------- #

FAKE_PI_SCRIPT = r'''
import json, sys
out = sys.stdout.buffer
out.write(json.dumps({"type": "hello", "text": "a b"}, ensure_ascii=False).encode() + b"\r\n")
out.write(b"not json\n")
out.flush()
for line in sys.stdin.buffer:
    record = json.loads(line)
    out.write(json.dumps({"type": "echo", "got": record}).encode() + b"\n")
    out.flush()
sys.stderr.write("bye\n")
'''


async def test_subprocess_transport_frames_records_on_lf_only(tmp_path):
    rpc = await SubprocessRpc.start([sys.executable, "-c", FAKE_PI_SCRIPT], tmp_path)

    first = await rpc.receive()
    await rpc.send({"type": "prompt", "message": "line sep"})
    second = await rpc.receive()
    await rpc.close()
    after = await rpc.receive()

    # U+2028 inside a JSON string is not a record boundary; bad lines are skipped.
    assert first == {"type": "hello", "text": "a b"}
    assert second == {"type": "echo", "got": {"type": "prompt", "message": "line sep"}}
    assert after is None
    assert "bye" in rpc.stderr_tail()


# --------------------------------------------------------------------------- #
# Registry wiring                                                             #
# --------------------------------------------------------------------------- #

def test_agent_mode_offers_claude_code_and_pi():
    from socra_server.__main__ import agent_backends

    assert [backend.id for backend in agent_backends()] == ["claude-code", "pi"]
