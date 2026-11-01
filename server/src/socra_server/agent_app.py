"""Application service for agent mode: Socra drives an agent by voice.

In exam mode the MCP client drives Socra. Here it is the other way around:
the page sends dictated turns, this service forwards them to the selected
AgentBackend, streams the reply back to the page and speaks the final answer.
Tool calls the backend wants approved are shown on the page as Allow / Deny.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from socra_server.adapters.turn_audio_log import save_turn_audio
from socra_server.adapters.whisper_stt import is_valid_answer
from socra_server.domain.scene import parse_scene
from socra_server.domain.walkthrough import parse_command
from socra_server.walkthrough import WalkthroughRunner
from socra_server.agent_registry import BackendRegistry, UnknownSelection
from socra_server.app import get_wav_duration
from socra_server.domain.agent import (
    AgentError,
    AgentSelection,
    PermissionRequest,
    ReplyDone,
    TextDelta,
    ToolActivity,
)
from socra_server.domain.handoff import (
    SUMMARY_PROMPT,
    HandoffSummary,
    InvalidSummary,
    SessionFacts,
    Turn,
    last_turns,
    parse_summary,
    render_seed,
    retry_prompt,
)
from socra_server.domain.modes import DEFAULT_MODE, UnknownMode, get_mode
from socra_server.domain.sentences import SentenceSplitter
from socra_server.domain.speakable import speakable_text
from socra_server.ports import AgentBackend, AgentConversation
from socra_server.socra_tools import CallbackToolbox

logger = logging.getLogger(__name__)

FolderPicker = Callable[[], str | None]
PLAYBACK_GRACE_S = 2.0
# One request plus two retries for a summary that lacks fields.
SUMMARY_ATTEMPTS = 3
NEEDS_CLAUDE_CODE = "Socra sessions need a backend with mentor and exam modes, such as Claude Code."
NO_AGENT_MODE = (
    "Coding agent mode is not available in Socra; it offers mentor and exam modes."
)


class AgentApp:
    def __init__(
        self,
        *,
        channel: Any,
        registry: BackendRegistry,
        loader: Any,
        folder_picker: FolderPicker,
        transcripts: Any = None,
    ) -> None:
        self.channel = channel
        self.registry = registry
        self.loader = loader
        self._folder_picker = folder_picker
        self._transcripts = transcripts
        self._conversation: AgentConversation | None = None
        self._backend: AgentBackend | None = None
        # What the page needs to resync after a reconnect; None without a conversation.
        self._session: dict[str, str] | None = None
        # Mode switching: what Socra records for the handoff, and the switch in flight.
        self._facts = SessionFacts()
        self._turns: list[Turn] = []
        self._transcript: Any = None
        self._previous_transcript: Any = None
        self._toolbox = CallbackToolbox(
            switch=self._tool_switch, record=self._tool_record, search=self._tool_search,
            play=self._tool_present,
        )
        self._switch_request: str | None = None
        # What the user said while a switch ran; the session that comes out of it answers it.
        self._switch_turns: list[str] = []
        self.switch_task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._start_task: asyncio.Task | None = None
        self._start_generation = 0
        self._queued_turn: str | None = None
        self._playback_done = asyncio.Event()
        self.turn_task: asyncio.Task | None = None
        self.acknowledged_clips = 0
        # The reply being spoken sentence by sentence; None between turns.
        self._speech: _ReplySpeech | None = None
        self._state_name = "idle"
        # Clips of an abandoned turn (interrupt, restart, shutdown) the page has not
        # reported yet; their late playback_done must not count toward the next turn.
        # Only the connected page can pay this debt, so a disconnect clears it.
        self._ack_debt = 0
        # Narrated scenes the mentor or exam agent plays with the present tool.
        self.walkthrough = WalkthroughRunner(
            synthesize=lambda text: self.loader.tts.synthesize(text),
            wav_duration=get_wav_duration,
            send=self.channel.send,
            set_state=self._state,
            is_connected=lambda: self.channel.is_connected,
        )

    # ------------------------------------------------------------------ #
    # Page -> server                                                       #
    # ------------------------------------------------------------------ #

    async def handle_hello(self) -> None:
        await self._send_hello()
        for message in self.walkthrough.snapshot():
            await self.channel.send(message)

    async def _send_hello(self) -> None:
        # Only backends that can host the mentor and exam modes are offered.
        infos = [info for info in await self.registry.describe() if info.supports_modes]
        default = next(
            (AgentSelection(info.id, info.models[0].id) for info in infos if info.models), None
        )
        await self.channel.send({
            "type": "agent_backends",
            "backends": [
                {
                    "id": info.id,
                    "label": info.label,
                    "models": [{"id": m.id, "label": m.label} for m in info.models],
                    "status": {"state": info.status.state, "message": info.status.message},
                    "supports_modes": info.supports_modes,
                }
                for info in infos
            ],
            "default": (
                {"backend": default.backend, "model": default.model} if default else None
            ),
            "session": self._session,
        })

    async def handle_pick_folder(self) -> None:
        path = await asyncio.to_thread(self._folder_picker)
        await self.channel.send({"type": "agent_folder", "path": path or None})

    async def handle_start(
        self, backend_id: str, model: str, cwd: str, mode: str = DEFAULT_MODE
    ) -> None:
        folder = Path(cwd)
        if not folder.is_dir():
            await self._error(f"Folder not found: {cwd}")
            return
        try:
            backend = self.registry.resolve(AgentSelection(backend_id, model))
            get_mode(mode)
        except (UnknownSelection, UnknownMode) as exc:
            await self._error(str(exc))
            return
        if not backend.supports_modes:
            await self._error(NEEDS_CLAUDE_CODE)
            return
        await self._cancel_switch()
        await self._cancel_turn()
        await self._cancel_start()
        await self._close_conversation()
        self._backend = backend
        self._facts = SessionFacts()
        self._turns = []
        self._previous_transcript = None
        self._transcript = self._transcripts.start(folder) if self._transcripts else None
        self._session = {"backend": backend_id, "model": model, "cwd": str(folder), "mode": mode}
        await self.channel.send({"type": "agent_started", **self._session})
        await self._state("idle")
        self._start_generation += 1
        generation = self._start_generation
        self._start_task = asyncio.create_task(
            self._open_start(backend, backend_id, model, folder, generation, mode),
            name="agent-start",
        )
        # Let the owned task begin without waiting for backend.open to finish.
        await asyncio.sleep(0)

    async def handle_turn_text(self, text: str) -> None:
        if not text.strip():
            return
        if self.walkthrough.active:
            await self._route_scene_speech(text)
            return
        if self._switching:
            self._switch_turns.append(text)
            return
        if await self._can_take_turn():
            if self._conversation is None and self._startup_pending:
                self._queued_turn = text
                await self._state("thinking")
            elif self._conversation is None:
                await self._error("Choose a folder and start a session first.")
            else:
                self._start_turn(text)

    def _stt_terms(self) -> list[str] | None:
        """Project-specific words to bias recognition: the open folder's name."""
        if not self._session:
            return None
        name = Path(self._session["cwd"]).name
        return [name] if name else None

    async def handle_turn_audio(self, b64_data: str) -> None:
        scene_playing = self.walkthrough.active
        if not scene_playing and not self._switching and not await self._can_take_turn():
            return
        starting = self._conversation is None
        try:
            wav_bytes = base64.b64decode(b64_data, validate=True)
        except (binascii.Error, ValueError):
            await self._error("Could not read the recorded audio.")
            await self._state("listening")
            return
        try:
            await self.loader.ready()
            text = await asyncio.to_thread(
                self.loader.stt.transcribe_with_glossary, wav_bytes, self._stt_terms()
            )
        except Exception as exc:
            logger.error("Agent turn transcription failed: %s", exc)
            await self._error("Could not transcribe the audio. Please try again.")
            await self._state("listening")
            return
        await asyncio.to_thread(save_turn_audio, wav_bytes, text or "")
        if not text or not is_valid_answer(text):
            await self.channel.send({"type": "notice", "text": "Didn't catch that. Please say it again."})
            await self._state("listening")
            return
        if scene_playing:
            await self.channel.send({"type": "transcript", "text": text, "final": True})
            await self._route_scene_speech(text)
            return
        if self._switching:
            await self.channel.send({"type": "transcript", "text": text, "final": True})
            self._switch_turns.append(text)
            return
        if self._turn_running or self._queued_turn is not None:
            await self.channel.send({
                "type": "notice", "text": "Wait for the current reply or interrupt it.",
            })
            return
        await self.channel.send({"type": "transcript", "text": text, "final": True})
        if self._conversation is None and starting and self._startup_pending:
            self._queued_turn = text
            await self._state("thinking")
        elif self._conversation is None:
            await self._error("The session is not ready. Please start it again.")
        elif self._conversation is not None:
            self._start_turn(text)

    async def handle_permission_response(self, request_id: str, allow: Any) -> None:
        future = self._pending.get(request_id)
        if future is not None and not future.done():
            future.set_result(allow is True)

    async def handle_interrupt(self) -> None:
        if self._switching:
            conversation = self._conversation
            await self._cancel_switch()
            if conversation is not None:
                try:
                    await conversation.interrupt()
                except Exception as exc:
                    logger.warning("Interrupting the mode switch failed: %s", exc)
            await self.channel.send({"type": "notice", "text": "Mode switch cancelled."})
            await self._switch_failed()
            return
        if self._start_task is not None and not self._start_task.done():
            await self._cancel_start()
            await self._close_conversation()
            await self.handle_hello()
            await self._state("idle")
            return
        if self.walkthrough.active:
            self.walkthrough.command("stop")
        if self._conversation is not None and self._turn_running:
            # Whatever is still being synthesized or queued must never sound.
            self._abandon_speech()
            await self._conversation.interrupt()

    def handle_playback_done(self, seq: int | None = None) -> None:
        """A clip finished on the page; scene steps carry a sequence number, replies do not."""
        if seq is not None:
            self.walkthrough.handle_playback_done(seq)
            return
        if self._ack_debt > 0:
            self._ack_debt -= 1
            return
        self.acknowledged_clips += 1
        self._playback_done.set()
        if self._speech is not None:
            self._speech.acknowledged()

    async def handle_walkthrough_control(self, action: object) -> None:
        """A scene control pressed on the page."""
        if action in ("pause", "resume", "repeat", "back", "next", "stop"):
            self.walkthrough.command(action)  # type: ignore[arg-type]

    async def handle_disconnect(self) -> None:
        self.walkthrough.abort()
        # The page that owed those acknowledgements is gone; a new page starts clean.
        self._ack_debt = 0
        self._playback_done.set()  # wake a wait for clips nobody can play any more
        # Nobody is left to answer: every open request becomes a denial.
        for future in self._pending.values():
            if not future.done():
                future.set_result(False)
        self._switch_request = None

    async def shutdown(self) -> None:
        await self.handle_disconnect()
        await self._cancel_switch()
        await self._cancel_start()
        await self._cancel_turn()
        await self._close_conversation()

    # ------------------------------------------------------------------ #
    # Turns                                                                #
    # ------------------------------------------------------------------ #

    @property
    def _turn_running(self) -> bool:
        return self.turn_task is not None and not self.turn_task.done()

    @property
    def _switching(self) -> bool:
        return self.switch_task is not None and not self.switch_task.done()

    @property
    def _startup_pending(self) -> bool:
        return self._start_task is not None and not self._start_task.done()

    async def _can_take_turn(self) -> bool:
        if self._switching:
            await self.channel.send({
                "type": "notice", "text": "Wait for the mode switch to finish.",
            })
            return False
        starting = self._startup_pending
        if self._conversation is None and not starting:
            await self._error("Choose a folder and start a session first.")
            return False
        if self._turn_running or self._queued_turn is not None:
            await self.channel.send({
                "type": "notice", "text": "Wait for the current reply or interrupt it.",
            })
            return False
        return True

    async def _open_conversation(self, backend, model: str, folder: Path, mode_id: str):
        return await backend.open(
            model, folder, self._decide_permission,
            mode=get_mode(mode_id), toolbox=self._toolbox,
        )

    async def _open_start(
        self, backend, backend_id: str, model: str, folder: Path, generation: int,
        mode_id: str = DEFAULT_MODE,
    ) -> None:
        try:
            conversation = await self._open_conversation(backend, model, folder, mode_id)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            if generation != self._start_generation:
                return
            logger.error("Could not start %s: %s", backend_id, exc)
            self._session = None
            self._queued_turn = None
            await self._error(f"Could not start {backend.label}: {exc}")
            await self.handle_hello()
            await self._state("idle")
            return
        if generation != self._start_generation:
            try:
                await conversation.close()
            except Exception as exc:
                logger.warning("Closing a stale agent conversation failed: %s", exc)
            return
        self._conversation = conversation
        queued_turn, self._queued_turn = self._queued_turn, None
        if queued_turn is not None:
            self._start_turn(queued_turn)
        else:
            await self._state("listening")

    async def _cancel_start(self) -> None:
        self._start_generation += 1
        self._queued_turn = None
        task, self._start_task = self._start_task, None
        if task is not None and not task.done():
            task.cancel()

    def _start_turn(self, text: str, *, hidden: bool = False) -> None:
        self.turn_task = asyncio.create_task(
            self._run_turn(text, hidden=hidden), name="agent-turn"
        )

    async def _cancel_turn(self) -> None:
        """Stop a running turn before its conversation goes away."""
        task = self.turn_task
        if task is None or task.done():
            return
        self._abandon_speech()
        if self._conversation is not None:
            try:
                await self._conversation.interrupt()
            except Exception as exc:
                logger.warning("Interrupting the agent turn failed: %s", exc)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    def _abandon_speech(self) -> None:
        """Stop the reply being spoken; the page still owes an ack for each clip it received."""
        speech = self._speech
        if speech is None or speech.cancelled:
            return  # already abandoned: its debt was taken then
        self._ack_debt += speech.unacknowledged()
        speech.cancel()

    async def _run_turn(self, text: str, *, hidden: bool = False) -> None:
        """Run one turn; a hidden turn (the handoff seed) is not recorded as a user turn."""
        conversation = self._conversation
        assert conversation is not None
        await self._state("thinking")
        if not hidden and self._transcript is not None:
            self._transcript.append("user", text)
        speech = self._speech = _ReplySpeech(self)
        try:
            async for event in conversation.send(text):
                if isinstance(event, TextDelta):
                    await self.channel.send({"type": "agent_text", "text": event.text})
                    speech.feed(event.text)
                elif isinstance(event, ToolActivity):
                    self._facts.record_tool(event)
                    # Words before a tool call sound now, not after the tool finishes.
                    speech.flush()
                    await self.channel.send({
                        "type": "agent_tool", "tool": event.tool, "summary": event.summary,
                    })
                elif isinstance(event, ReplyDone):
                    if self._transcript is not None:
                        self._transcript.append("agent", event.text)
                    if not hidden:
                        self._turns.append(Turn(text, event.text))
                    await self.channel.send({"type": "agent_reply", "text": event.text})
                    if not speech.fed:
                        speech.feed(event.text)
                    speech.flush()
                    await speech.finish()
                elif isinstance(event, AgentError):
                    await self._error(event.message)
        except Exception as exc:
            logger.exception("Agent turn failed")
            await self._error(f"The agent turn failed: {exc}")
        finally:
            speech.cancel()
            if self._speech is speech:
                self._speech = None
            await self._state("listening")

    async def _decide_permission(self, request: PermissionRequest) -> bool:
        if not self.channel.is_connected:
            return False
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._pending[request.request_id] = future
        try:
            await self.channel.send({
                "type": "permission_request",
                "id": request.request_id,
                "tool": request.tool,
                "title": request.title,
                "detail": request.detail,
            })
            allowed = await future
            self._facts.record_permission(request.tool, request.title, allowed)
            return allowed
        except asyncio.CancelledError:
            # The turn was interrupted or restarted: take the prompt off the page.
            await self.channel.send({"type": "permission_closed", "id": request.request_id})
            raise
        finally:
            self._pending.pop(request.request_id, None)

    # ------------------------------------------------------------------ #
    # Mode switching                                                       #
    # ------------------------------------------------------------------ #

    async def handle_switch_mode(self, target: str) -> None:
        """The user picked a mode in the selector: switch at once."""
        if await self._switch_problem(target):
            return
        self.switch_task = asyncio.create_task(self._run_switch(target), name="agent-switch")
        await asyncio.sleep(0)

    async def handle_mode_switch_response(self, target: str, allow: Any) -> None:
        """The user answered the on-screen confirmation of a voice-requested switch."""
        if self._switch_request != target:
            return
        self._switch_request = None
        if allow is not True:
            await self.channel.send({"type": "mode_switch_closed", "mode": target})
            return
        await self.handle_switch_mode(target)

    async def _switch_problem(self, target: str) -> str | None:
        """Report why a switch cannot start (to the page), or None when it can."""
        try:
            mode = get_mode(target)
        except UnknownMode as exc:
            await self._error(str(exc))
            return str(exc)
        if self._conversation is None and self._startup_pending:
            text = "Wait for the session to start, then switch modes."
            await self.channel.send({"type": "notice", "text": text})
            return text
        if self._backend is None or self._conversation is None or self._session is None:
            await self._error("Choose a folder and start a session first.")
            return "no session"
        if target == self._session["mode"]:
            text = f"Already in {mode.label} mode."
            await self.channel.send({"type": "notice", "text": text})
            return text
        if self._switching:
            text = "A mode switch is already running."
            await self.channel.send({"type": "notice", "text": text})
            return text
        return None

    async def _run_switch(self, target: str) -> None:
        assert self._session is not None and self._backend is not None
        mode = get_mode(target)
        session = self._session
        await self.channel.send({"type": "agent_switching", "mode": target})
        await self._state("thinking")
        # A voice request can arrive while the agent is still answering: let it finish.
        running = self.turn_task
        if running is not None and not running.done():
            await asyncio.wait({running})
        old = self._conversation
        assert old is not None
        summary = await self._request_summary(old)
        if summary is None:
            await self._error(
                f"Could not switch to {mode.label} mode: the agent did not produce a "
                "valid summary. You stay in the current mode."
            )
            await self._switch_failed()
            return
        try:
            new = await self._open_conversation(
                self._backend, session["model"], Path(session["cwd"]), target
            )
        except Exception as exc:
            logger.error("Could not start %s mode: %s", target, exc)
            await self._error(
                f"Could not start {mode.label} mode: {exc}. You stay in the current mode."
            )
            await self._switch_failed()
            return
        # The new session is up: adopt it first, so a failure to close the old one
        # can never leave the app without a conversation.
        self._conversation = new
        self._session = {**session, "mode": target}
        self._previous_transcript = self._transcript
        self._transcript = self._transcripts.start(session["cwd"]) if self._transcripts else None
        await self.channel.send({"type": "agent_mode_changed", **self._session})
        try:
            await old.close()
        except Exception as exc:
            logger.warning("Closing the previous agent session failed: %s", exc)
        # Read only now: the user can keep talking until the new session takes over.
        pending, self._switch_turns = self._switch_turns, []
        if self._transcript is not None:
            for text in pending:
                self._transcript.append("user", text)
        seed = render_seed(mode, self._facts, summary, last_turns(self._turns), pending)
        self._start_turn(seed, hidden=True)

    async def _request_summary(self, conversation: AgentConversation) -> HandoffSummary | None:
        prompt = SUMMARY_PROMPT
        for _ in range(SUMMARY_ATTEMPTS):
            reply = await self._silent_turn(conversation, prompt)
            if reply is None:
                prompt = SUMMARY_PROMPT
                continue
            try:
                return parse_summary(reply)
            except InvalidSummary as exc:
                prompt = retry_prompt(exc.missing)
        return None

    async def _silent_turn(self, conversation: AgentConversation, prompt: str) -> str | None:
        """Run a turn nobody sees or hears; the reply text, or None when it failed."""
        reply: str | None = None
        try:
            async for event in conversation.send(prompt):
                if isinstance(event, ToolActivity):
                    self._facts.record_tool(event)
                elif isinstance(event, ReplyDone):
                    reply = event.text
                elif isinstance(event, AgentError):
                    logger.warning("Handoff summary turn failed: %s", event.message)
                    return None
        except Exception as exc:
            logger.warning("Handoff summary turn raised: %s", exc)
            return None
        return reply

    async def _switch_failed(self) -> None:
        mode = self._session["mode"] if self._session else DEFAULT_MODE
        await self.channel.send({"type": "mode_switch_failed", "mode": mode})
        # The old session is still open: it answers what the user said meanwhile.
        pending, self._switch_turns = self._switch_turns, []
        if pending and self._conversation is not None:
            self._start_turn("\n".join(pending))
        else:
            await self._state("listening")

    async def _cancel_switch(self) -> None:
        self._switch_request = None
        self._switch_turns = []
        task, self.switch_task = self.switch_task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # The Socra tools the agent can call (see socra_tools).

    async def _tool_switch(self, target: str) -> str:
        if target == "agent":
            return NO_AGENT_MODE
        try:
            mode = get_mode(target)
        except UnknownMode:
            return "Use mentor or exam."
        if self._session is not None and target == self._session["mode"]:
            return f"Already in {mode.label} mode."
        if self._switching:
            return "A mode switch is already running."
        if self._switch_request and self._switch_request != target:
            await self.channel.send({"type": "mode_switch_closed", "mode": self._switch_request})
        self._switch_request = target
        await self.channel.send({
            "type": "mode_switch_request", "mode": target, "label": mode.label,
        })
        return (
            f"Asked the user to confirm switching to {mode.label} mode. Tell them you asked "
            "and wait; the switch happens only if they accept."
        )

    async def _tool_record(self, question: str, verdict: str, note: str) -> str:
        self._facts.record_exam_result(question, verdict, note)
        return "Recorded."

    async def _tool_present(self, scene: Any) -> str:
        parsed, errors = parse_scene(scene)
        if parsed is None:
            return json.dumps({"status": "invalid", "errors": errors})
        if not self.channel.is_connected:
            return json.dumps({"status": "page_disconnected"})
        if self.walkthrough.active:
            return json.dumps({"status": "busy"})
        await self.loader.ready()
        if self._speech is not None:
            # The scene must not cut or interleave with the words said just before it.
            self._speech.flush()
            await self._speech.settle()
            if self._speech is None or self._speech.cancelled:
                # Interrupted while waiting: end it as main does when stopped at step 1.
                return json.dumps({"status": "stopped", "step": 1, "total": len(parsed.steps)})
            if not self.channel.is_connected:
                return json.dumps({"status": "page_disconnected"})
        result = await self.walkthrough.run(parsed)
        # The agent's turn goes on after the scene.
        await self._state("thinking" if self._turn_running else "listening")
        return json.dumps(result)

    async def _route_scene_speech(self, text: str) -> None:
        """While a scene plays, what the user says or types steers it instead of starting a turn."""
        command = parse_command(text)
        if command is not None:
            self.walkthrough.command(command)
            return
        await self.channel.send({
            "type": "notice",
            "text": "Say or type repeat, back, next, continue or stop.",
        })
        if self.walkthrough.paused:
            await self._state("listening")

    async def _tool_search(self, query: str, limit: int) -> list[Any]:
        if self._previous_transcript is None:
            return []
        return await asyncio.to_thread(self._previous_transcript.search, query, limit)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    async def _close_conversation(self) -> None:
        conversation, self._conversation = self._conversation, None
        self._session = None
        if conversation is not None:
            try:
                await conversation.close()
            except Exception as exc:
                logger.warning("Closing the agent conversation failed: %s", exc)

    async def _state(self, state: str) -> None:
        self._state_name = state
        await self.channel.send({"type": "state", "state": state})

    async def _error(self, message: str) -> None:
        await self.channel.send({"type": "agent_error", "message": message})


class _ReplySpeech:
    """Speaks one agent reply sentence by sentence while it streams.

    ``feed`` and ``flush`` only queue text; a worker synthesizes the pieces in
    order and sends each clip as soon as it is ready, so the page can queue them
    back to back. ``finish`` returns once the page has played every clip.
    """

    def __init__(self, app: AgentApp) -> None:
        self._app = app
        self._splitter = SentenceSplitter()
        self._queue: asyncio.Queue[str | None] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._base_acks = app.acknowledged_clips
        self._sent = 0
        self._outstanding = 0  # pieces queued or being synthesized, not yet sent or skipped
        self._progress = asyncio.Event()
        self._play_end = 0.0
        self._cancelled = False
        self._closed = False
        self._failures = 0
        self._notices: set[asyncio.Task] = set()
        self.fed = False

    def feed(self, text: str) -> None:
        if self._cancelled or self._closed:
            return
        self.fed = True
        self._enqueue(self._splitter.feed(text))

    def flush(self) -> None:
        """Release the unfinished sentence (a tool call started or the reply ended)."""
        if self._cancelled or self._closed:
            return
        self._enqueue(self._splitter.flush())

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def unacknowledged(self) -> int:
        """Clips already sent that the page has not reported as played."""
        return max(0, self._sent - (self._app.acknowledged_clips - self._base_acks))

    def cancel(self) -> None:
        """Drop pending synthesis and every later clip; wake any waiter."""
        self._cancelled = True
        if self._worker is not None and not self._worker.done():
            self._worker.cancel()
        while not self._queue.empty():
            self._queue.get_nowait()
        self._outstanding = 0
        self._progress.set()
        self._app._playback_done.set()

    async def settle(self) -> None:
        """Wait until everything queued so far has been sent and played."""
        await self._wait_for_sent()
        await self._wait_for_playback()

    async def finish(self) -> None:
        """Wait until the worker has sent every clip and the page has played them."""
        self._closed = True
        if self._worker is not None:
            self._queue.put_nowait(None)
            await asyncio.gather(self._worker, return_exceptions=True)
        await self._wait_for_playback()
        if self._failures and not self._cancelled:
            await self._app._error("Part of the reply could not be spoken.")

    def acknowledged(self) -> None:
        """The page played a clip: with nothing left to say, the agent is working again."""
        if self._cancelled or self._closed or self._outstanding or self.unacknowledged():
            return
        task = asyncio.get_running_loop().create_task(self._back_to_thinking())
        self._notices.add(task)
        task.add_done_callback(self._notices.discard)

    async def _back_to_thinking(self) -> None:
        if (
            self._app._speech is self and not self._cancelled and not self._closed
            and not self._outstanding and not self.unacknowledged()
            and self._app._state_name == "speaking"
        ):
            await self._app._state("thinking")

    def _enqueue(self, pieces: list[str]) -> None:
        for piece in pieces:
            spoken = speakable_text(piece)
            if not spoken:
                continue
            self._outstanding += 1
            self._queue.put_nowait(spoken)
            if self._worker is None:
                self._worker = asyncio.create_task(self._run(), name="agent-speech")

    def _settled_one(self) -> None:
        if self._outstanding > 0:
            self._outstanding -= 1
        self._progress.set()

    def _fail(self, exc: Exception) -> None:
        logger.error("Speaking part of the agent reply failed: %s", exc)
        self._failures += 1

    async def _run(self) -> None:
        app = self._app
        ready = True
        try:
            await app.loader.ready()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._fail(exc)
            ready = False
        done = False
        while not done and (first := await self._queue.get()) is not None:
            # Everything complete by now goes out as one clip (#85 S13); the first
            # sentence of a stream is alone in the queue, so it still starts at once.
            pieces = [first]
            while not self._queue.empty():
                nxt = self._queue.get_nowait()
                if nxt is None:
                    done = True
                    break
                pieces.append(nxt)
            spoken = " ".join(pieces)
            try:
                if not ready:
                    continue
                wav = await asyncio.to_thread(app.loader.tts.synthesize, spoken)
                if self._cancelled:
                    return
                if not app.channel.is_connected:
                    continue  # nobody receives it, so nobody will report it as played
                if app._state_name != "speaking":
                    await app._state("speaking")
                self._sent += 1
                loop = asyncio.get_running_loop()
                self._play_end = max(loop.time(), self._play_end) + get_wav_duration(wav)
                await app.channel.send({
                    "type": "tts_audio", "format": "wav",
                    "data": base64.b64encode(wav).decode(),
                })
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._fail(exc)  # skip this sentence, keep speaking the next ones
            finally:
                for _ in pieces:
                    self._settled_one()

    async def _wait_for_sent(self) -> None:
        while not self._cancelled and self._outstanding:
            self._progress.clear()
            if not self._outstanding:
                break
            await self._progress.wait()

    async def _wait_for_playback(self) -> None:
        app = self._app
        loop = asyncio.get_running_loop()
        while (
            not self._cancelled and app.channel.is_connected
            and app.acknowledged_clips - self._base_acks < self._sent
        ):
            app._playback_done.clear()
            if self._cancelled or app.acknowledged_clips - self._base_acks >= self._sent:
                break
            remaining = max(0.0, self._play_end - loop.time()) + PLAYBACK_GRACE_S
            try:
                await asyncio.wait_for(app._playback_done.wait(), timeout=remaining)
            except TimeoutError:
                logger.warning("Agent reply playback wait timed out")
                return
