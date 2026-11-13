"""Live (provisional) transcript: partial decodes while the user speaks, never after the final."""
from __future__ import annotations

import asyncio
import base64
import threading

from socra_server import agent_app as agent_app_module
from tests.test_agent_app import _app, _wav


def _b64(seconds: float) -> str:
    return base64.b64encode(_wav(seconds)).decode()


class PartialSTT:
    """Records partial decodes; each can be held open on a gate to model a slow model."""

    def __init__(self, final: str = "list the files") -> None:
        self.final = final
        self.partial_sizes: list[int] = []
        self.finals = 0
        self.fail = False
        self.gate = threading.Event()
        self.gate.set()
        self.started = threading.Event()

    def transcribe_partial(self, wav_bytes: bytes, glossary) -> str:
        self.partial_sizes.append(len(wav_bytes))
        self.started.set()
        self.gate.wait(timeout=5)
        if self.fail:
            raise RuntimeError("model exploded")
        return f"partial {len(wav_bytes)}"

    def transcribe_with_glossary(self, wav_bytes: bytes, glossary) -> str:
        self.finals += 1
        return self.final


async def _until(condition, timeout: float = 2.0) -> None:
    for _ in range(int(timeout / 0.005)):
        if condition():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not reached in time")


def _partials(channel) -> list[dict]:
    return [m for m in channel.of_type("transcript") if m["final"] is False]


async def _started(tmp_path):
    app, channel, backend, loader = _app()
    loader.stt = PartialSTT()
    await app.handle_start("fake", "small", str(tmp_path))
    return app, channel, backend, loader.stt


async def test_a_partial_is_decoded_and_shown_as_not_final(tmp_path):
    app, channel, _, stt = await _started(tmp_path)

    await app.handle_turn_audio_partial(_b64(0.1))
    await _until(lambda: _partials(channel))

    assert _partials(channel) == [{"type": "transcript", "text": f"partial {len(_wav(0.1))}", "final": False}]
    assert channel.of_type("error") == []


async def test_only_the_newest_pending_partial_is_decoded(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    stt.gate.clear()

    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.to_thread(stt.started.wait, 2)
    await app.handle_turn_audio_partial(_b64(0.2))
    await app.handle_turn_audio_partial(_b64(0.3))
    stt.gate.set()
    await _until(lambda: len(_partials(channel)) == 2)
    await asyncio.sleep(0.05)

    assert stt.partial_sizes == [len(_wav(0.1)), len(_wav(0.3))]


async def test_no_partial_is_shown_after_the_final_started(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    stt.gate.clear()
    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.to_thread(stt.started.wait, 2)

    await app.handle_turn_audio(_b64(0.5), review=True)
    stt.gate.set()
    await asyncio.sleep(0.1)

    assert _partials(channel) == []
    assert channel.of_type("transcript_draft") == [{"type": "transcript_draft", "text": "list the files"}]


async def test_the_final_does_not_wait_for_queued_partials(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    stt.gate.clear()
    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.to_thread(stt.started.wait, 2)
    await app.handle_turn_audio_partial(_b64(0.2))

    await asyncio.wait_for(app.handle_turn_audio(_b64(0.5), review=True), timeout=1)
    stt.gate.set()
    await asyncio.sleep(0.1)

    assert stt.finals == 1
    assert stt.partial_sizes == [len(_wav(0.1))]  # the queued one was dropped


async def test_a_partial_that_fails_is_swallowed(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    stt.fail = True

    await app.handle_turn_audio_partial(_b64(0.1))
    await _until(lambda: stt.partial_sizes)
    await asyncio.sleep(0.05)
    stt.fail = False
    await app.handle_turn_audio_partial(_b64(0.2))
    await _until(lambda: _partials(channel))

    assert channel.of_type("error") == []
    assert channel.of_type("notice") == []


async def test_undecodable_partial_audio_is_ignored_silently(tmp_path):
    app, channel, _, stt = await _started(tmp_path)

    await app.handle_turn_audio_partial("not base64!!")
    await asyncio.sleep(0.05)

    assert stt.partial_sizes == []
    assert channel.of_type("error") == []


async def test_no_partial_without_a_session_to_take_the_turn():
    app, channel, _, loader = _app()
    loader.stt = PartialSTT()

    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.sleep(0.05)

    assert loader.stt.partial_sizes == []
    assert channel.sent == []


async def test_no_partial_while_a_turn_is_waiting(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    app._queued_turn = "already waiting"

    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.sleep(0.05)

    assert stt.partial_sizes == []
    assert channel.of_type("transcript") == []


async def test_partial_audio_is_never_saved(tmp_path, monkeypatch):
    saved: list[bytes] = []
    monkeypatch.setattr(agent_app_module, "save_turn_audio", lambda wav, text: saved.append(wav))
    app, channel, _, stt = await _started(tmp_path)

    await app.handle_turn_audio_partial(_b64(0.1))
    await _until(lambda: _partials(channel))

    assert saved == []


async def test_a_partial_decoded_after_the_page_left_never_reaches_the_next_page(tmp_path):
    # review R3-partial-task-not-cancelled: the decode outlives the page that asked for it
    app, channel, _, stt = await _started(tmp_path)
    stt.gate.clear()
    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.to_thread(stt.started.wait, 2)

    await app.handle_disconnect()
    stt.gate.set()
    await asyncio.sleep(0.1)

    assert _partials(channel) == []


async def test_shutdown_stops_the_partial_worker(tmp_path):
    app, channel, _, stt = await _started(tmp_path)
    stt.gate.clear()
    await app.handle_turn_audio_partial(_b64(0.1))
    await asyncio.to_thread(stt.started.wait, 2)

    await app.shutdown()
    stt.gate.set()

    assert app._partial_task is None or app._partial_task.done()
