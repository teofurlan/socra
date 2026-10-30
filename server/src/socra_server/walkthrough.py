"""Plays a narrated scene: one clip per step, the step's visual state sent with its audio.

The runner is independent of MCP and of the page transport: it is given a
synthesizer, a way to send page messages and a way to set the turn state, so
any entrypoint (the exam MCP tools today, an agent session tool server later)
can drive it.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Awaitable, Callable

from socra_server.domain.scene import Scene
from socra_server.domain.walkthrough import Command, StepCursor

logger = logging.getLogger(__name__)

PLAYBACK_GRACE_S = 2.0
_GONE = "gone"


class WalkthroughRunner:
    def __init__(
        self,
        *,
        synthesize: Callable[[str], bytes],
        wav_duration: Callable[[bytes], float],
        send: Callable[[dict], Awaitable[None]],
        set_state: Callable[[str], Awaitable[None]],
        is_connected: Callable[[], bool],
    ) -> None:
        self._synthesize = synthesize
        self._wav_duration = wav_duration
        self._send = send
        self._set_state = set_state
        self._is_connected = is_connected
        self._active = False
        self._paused = False
        self._scene: Scene | None = None
        self._cursor: StepCursor | None = None
        self._commands: asyncio.Queue[str] = asyncio.Queue()
        self._seq = 0
        self._done = asyncio.Event()

    # ------------------------------------------------------------------ #
    # Page-facing surface                                                  #
    # ------------------------------------------------------------------ #

    @property
    def active(self) -> bool:
        return self._active

    @property
    def paused(self) -> bool:
        return self._paused

    def command(self, command: Command) -> None:
        """A user command (button, voice or typed); ignored when nothing is playing."""
        if self._active:
            self._commands.put_nowait(command)

    def abort(self) -> None:
        """The page is gone: end the walkthrough instead of waiting for it."""
        if self._active:
            self._commands.put_nowait(_GONE)

    def handle_playback_done(self, seq: int) -> None:
        """The page finished (or stopped) a clip; only the current clip counts."""
        if seq == self._seq:
            self._done.set()

    def snapshot(self) -> list[dict]:
        """Messages that bring a newly connected page up to the current step."""
        if not self._active or self._scene is None or self._cursor is None:
            return []
        scene = self._scene
        return [
            self._walkthrough_message(scene),
            self._step_info(scene, self._cursor.index) | {"type": "walkthrough_step"},
            {"type": "walkthrough_status", "status": "paused" if self._paused else "playing"},
        ]

    # ------------------------------------------------------------------ #
    # Playback                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _walkthrough_message(scene: Scene) -> dict:
        return {"type": "walkthrough", "title": scene.title, "objects": scene.objects_for_page(), "total": len(scene.steps)}

    @staticmethod
    def _step_info(scene: Scene, index: int) -> dict:
        return {
            "index": index + 1,
            "total": len(scene.steps),
            "id": scene.steps[index].id,
            "say": scene.steps[index].say,
            "state": scene.state_at(index),
        }

    async def run(self, scene: Scene) -> dict:
        """Play every step; return how it ended."""
        if self._active:
            return {"status": "busy"}
        total = len(scene.steps)
        self._active = True
        self._paused = False
        self._scene = scene
        self._cursor = StepCursor(total=total)
        self._commands = asyncio.Queue()
        try:
            await self._send(self._walkthrough_message(scene))
            await self._send({"type": "walkthrough_status", "status": "playing"})
            next_event: str | None = None
            while True:
                event = next_event or await self._play_current()
                next_event = None
                if event == "pause":
                    event = await self._wait_while_paused()
                if event == _GONE:
                    await self._end("disconnected")
                    return {"status": "page_disconnected", "step": self._cursor.index + 1, "total": total}
                outcome = self._cursor.advance() if event == "done" else self._cursor.apply(event)  # type: ignore[arg-type]
                if outcome == "play":
                    continue
                reason = "completed" if outcome == "finished" else "stopped"
                at = self._cursor.index + 1
                await self._end(reason)
                if outcome == "finished":
                    return {"status": "completed", "steps": total}
                return {"status": "stopped", "step": at, "total": total}
        except asyncio.CancelledError:
            # The caller gave up on the scene (an agent turn was interrupted): close the page's panel.
            await self._end("stopped")
            raise
        except Exception as exc:
            logger.exception("Walkthrough failed at step %d", self._cursor.index + 1)
            at = self._cursor.index + 1
            await self._end("error")
            return {"status": "error", "step": at, "total": total, "message": str(exc)}
        finally:
            self._active = False
            self._paused = False
            self._scene = None
            self._cursor = None

    async def _end(self, reason: str) -> None:
        await self._send({"type": "walkthrough_status", "status": "ended", "reason": reason})
        await self._set_state("idle")

    async def _play_current(self) -> str:
        """Speak the current step. Returns "done" or the command that cut it short."""
        assert self._scene is not None and self._cursor is not None
        index = self._cursor.index
        step = self._scene.steps[index]
        await self._set_state("speaking")
        wav = await asyncio.to_thread(self._synthesize, step.say)
        if not self._commands.empty():  # the user acted while this step was being prepared
            return self._commands.get_nowait()
        self._seq += 1
        self._done.clear()
        message = {
            "type": "tts_audio",
            "format": "wav",
            "data": base64.b64encode(wav).decode(),
            "step": self._step_info(self._scene, index) | {"seq": self._seq},
        }
        await self._send(message)

        timeout = self._wav_duration(wav) + PLAYBACK_GRACE_S
        played = asyncio.ensure_future(self._done.wait())
        command = asyncio.ensure_future(self._commands.get())
        try:
            finished, _ = await asyncio.wait({played, command}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (played, command):
                if not task.done():
                    task.cancel()
        if command in finished:
            return command.result()
        if played not in finished:
            logger.warning("Walkthrough step %d playback wait timed out after %.2f s", index + 1, timeout)
        return "done" if self._is_connected() else _GONE

    async def _wait_while_paused(self) -> str:
        """Listen for a command; returns it (never "pause") or the loss of the page."""
        self._paused = True
        await self._send({"type": "walkthrough_status", "status": "paused"})
        await self._set_state("listening")
        try:
            while True:
                command = await self._commands.get()
                if command != "pause":
                    break
        finally:
            self._paused = False
        if command != _GONE and command != "stop":
            await self._send({"type": "walkthrough_status", "status": "playing"})
        return command
