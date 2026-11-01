"""Agent replies are spoken sentence by sentence while they stream (issue #60)."""
from __future__ import annotations

import asyncio
import json
import threading

from socra_server.domain.agent import AgentError, ReplyDone, TextDelta, ToolActivity
from tests.test_agent_app import FakeBackend, ScriptedConversation, _app


class LiveConversation(ScriptedConversation):
    """Yields events as the test pushes them, like a backend that is still writing."""

    def __init__(self, decide) -> None:
        super().__init__([], decide)
        self.events: asyncio.Queue = asyncio.Queue()

    async def send(self, text: str):
        self.turns.append(text)
        while True:
            event = await self.events.get()
            yield event
            if isinstance(event, (ReplyDone, AgentError)):
                return


async def _live(tmp_path):
    backend = FakeBackend()
    app, channel, _, loader = _app(backend)

    async def open_live(model, cwd, decide, *, mode=None, toolbox=None):
        conversation = LiveConversation(decide)
        backend.conversations.append(conversation)
        conversation.toolbox = toolbox
        return conversation

    backend.open = open_live
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()
    await app.handle_turn_text("explain")
    await asyncio.sleep(0)
    return app, channel, loader, backend.conversations[0]


async def _until(condition, timeout: float = 2.0) -> None:
    """Wait for a condition instead of sleeping a fixed time (synthesis runs in a thread)."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


async def _settle() -> None:
    # Let the event loop and the synthesis thread go quiet before asserting a negative.
    for _ in range(6):
        await asyncio.sleep(0.01)


def _states(channel) -> list[str]:
    return [m["state"] for m in channel.of_type("state")]


async def test_first_sentence_is_spoken_before_the_reply_finishes(tmp_path):  # S1
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(TextDelta("First sentence. Second par"))
    await _until(lambda: len(channel.of_type("tts_audio")) == 1)

    assert loader.tts.spoken == ["First sentence."]
    assert len(channel.of_type("tts_audio")) == 1
    assert not app.turn_task.done()
    assert channel.of_type("agent_reply") == []

    await convo.events.put(TextDelta("t."))
    await convo.events.put(ReplyDone("First sentence. Second part."))
    await _settle()
    app.handle_playback_done()
    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)

    assert loader.tts.spoken == ["First sentence.", "Second part."]


async def test_text_before_a_tool_call_is_spoken_when_the_tool_starts(tmp_path):  # S2
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(TextDelta("Voy a verificarlo en la memoria de esa sesión"))
    await _settle()
    assert loader.tts.spoken == []  # no sentence end yet, nothing forces it out

    await convo.events.put(ToolActivity("mem_search", "sesión"))
    await _settle()

    assert loader.tts.spoken == ["Voy a verificarlo en la memoria de esa sesión"]
    assert len(channel.of_type("tts_audio")) == 1
    assert not app.turn_task.done()  # the agent is still working
    await app.shutdown()


async def test_clips_go_out_in_order_and_listening_waits_for_the_last_ack(tmp_path):  # S3
    app, channel, loader, convo = await _live(tmp_path)
    text = "One. Two. Three."

    await convo.events.put(TextDelta(text))
    await convo.events.put(ReplyDone(text))
    await _settle()

    assert loader.tts.spoken == ["One.", "Two.", "Three."]
    assert len(channel.of_type("tts_audio")) == 3  # all queued on the page at once
    app.handle_playback_done()
    app.handle_playback_done()
    await _settle()
    assert "listening" not in _states(channel)
    assert not app.turn_task.done()

    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)

    assert _states(channel) == ["thinking", "speaking", "listening"]
    assert _states(channel).count("speaking") == 1


async def test_code_and_markdown_markers_are_not_spoken_per_sentence(tmp_path):  # S4
    app, channel, loader, convo = await _live(tmp_path)
    text = "## Plan\n\n**Run** `ls`. Then:\n```py\nprint('a. b')\n```\nSee [docs](http://x). Done."

    await convo.events.put(TextDelta(text))
    await convo.events.put(ReplyDone(text))
    await _settle()

    assert loader.tts.spoken == ["Plan", "Run ls.", "Then:", "See docs.", "Done."]
    await app.shutdown()


async def test_interrupt_discards_pending_synthesis_and_later_clips(tmp_path):  # S5
    app, channel, loader, convo = await _live(tmp_path)
    gate = threading.Event()
    real = loader.tts.synthesize

    def slow(text: str) -> bytes:
        if text == "Two.":
            gate.wait(timeout=2)
        return real(text)

    loader.tts.synthesize = slow

    await convo.events.put(TextDelta("One. Two. Three. "))
    await _settle()
    assert len(channel.of_type("tts_audio")) == 1  # "Two." is still being synthesized

    await app.handle_interrupt()
    gate.set()
    await convo.events.put(TextDelta("Four. "))
    await convo.events.put(ReplyDone("One. Two. Three. Four."))
    await asyncio.wait_for(app.turn_task, timeout=2)
    await _settle()

    assert len(channel.of_type("tts_audio")) == 1
    assert "Three." not in loader.tts.spoken and "Four." not in loader.tts.spoken
    assert _states(channel)[-1] == "listening"


async def test_the_final_reply_message_is_unchanged(tmp_path):  # S6
    app, channel, _, convo = await _live(tmp_path)
    reply = "Look at `x`.\n```py\nx = 1\n```\nDone."

    await convo.events.put(TextDelta(reply))
    await convo.events.put(ReplyDone(reply))
    await _settle()

    assert channel.of_type("agent_reply") == [{"type": "agent_reply", "text": reply}]
    assert channel.of_type("agent_text") == [{"type": "agent_text", "text": reply}]
    await app.shutdown()


async def test_a_single_sentence_reply_is_one_clip_then_listening(tmp_path):  # existing behavior
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(TextDelta("All good."))
    await convo.events.put(ReplyDone("All good."))
    await _settle()
    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)

    assert loader.tts.spoken == ["All good."]
    assert len(channel.of_type("tts_audio")) == 1
    assert _states(channel) == ["thinking", "speaking", "listening"]


async def test_a_reply_without_streamed_text_is_still_spoken_by_sentence(tmp_path):
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(ReplyDone("Alpha. Beta."))
    await _settle()
    app.handle_playback_done()
    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)

    assert loader.tts.spoken == ["Alpha.", "Beta."]


SCENE = {
    "version": 1,
    "title": "Adding",
    "objects": [{"id": "src", "primitive": "code", "params": {"code": "a = 1", "language": "python"}}],
    "steps": [{"id": "one", "say": "Look here."}, {"id": "two", "say": "And here."}],
    "cues": [],
}


def _reply_clips(channel) -> list[dict]:
    return [m for m in channel.of_type("tts_audio") if "step" not in m]


def _scene_clips(channel) -> list[dict]:
    return [m for m in channel.of_type("tts_audio") if "step" in m]


async def _ack_scene(app, channel) -> None:
    acked: set[int] = set()
    while app.walkthrough.active:
        for message in _scene_clips(channel):
            seq = message["step"]["seq"]
            if seq not in acked:
                acked.add(seq)
                app.handle_playback_done(seq)
        await asyncio.sleep(0.005)


async def test_a_scene_waits_for_the_sentence_before_it_and_later_clips_go_out_speaking(tmp_path):  # S6
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("Let me show you. "))
    await _until(lambda: len(_reply_clips(channel)) == 1)

    scene = asyncio.create_task(convo.toolbox.present(SCENE))
    await _settle()
    assert _scene_clips(channel) == []  # the sentence is still playing: the scene must not cut it

    app.handle_playback_done()
    await _until(lambda: len(_scene_clips(channel)) >= 1)
    await asyncio.wait_for(_ack_scene(app, channel), timeout=2)
    await asyncio.wait_for(scene, timeout=2)

    await convo.events.put(TextDelta("Now you know. "))
    await _until(lambda: len(_reply_clips(channel)) == 2)
    after = channel.sent[: channel.sent.index(_reply_clips(channel)[1])]
    assert [m["state"] for m in after if m["type"] == "state"][-1] == "speaking"
    await app.shutdown()


async def test_state_goes_back_to_thinking_when_the_clips_end_but_tools_still_run(tmp_path):  # regression vs main
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(TextDelta("Checking now. "))
    await convo.events.put(ToolActivity("mem_search", "x"))
    await _until(lambda: len(channel.of_type("tts_audio")) == 1)
    assert _states(channel)[-1] == "speaking"

    app.handle_playback_done()
    await _until(lambda: _states(channel)[-1] == "thinking")
    assert not app.turn_task.done()
    await app.shutdown()


async def test_a_late_ack_from_an_interrupted_turn_does_not_count_for_the_next_turn(tmp_path):  # S5
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("One. Two. "))
    await _until(lambda: len(channel.of_type("tts_audio")) == 2)
    await app.handle_interrupt()
    await convo.events.put(ReplyDone("One. Two."))
    await asyncio.wait_for(app.turn_task, timeout=2)

    await app.handle_turn_text("again")
    await convo.events.put(TextDelta("Next. "))
    await convo.events.put(ReplyDone("Next."))
    await _until(lambda: len(channel.of_type("tts_audio")) == 3)

    app.handle_playback_done()  # the page reports the two interrupted clips late
    app.handle_playback_done()
    await _settle()
    assert not app.turn_task.done()
    assert _states(channel)[-1] != "listening"

    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)
    assert _states(channel)[-1] == "listening"


async def test_a_sentence_that_fails_to_synthesize_is_skipped_and_reported_once(tmp_path):  # S3
    app, channel, loader, convo = await _live(tmp_path)
    real = loader.tts.synthesize

    def flaky(text: str) -> bytes:
        if text == "Two.":
            raise RuntimeError("boom")
        return real(text)

    loader.tts.synthesize = flaky
    await convo.events.put(TextDelta("One. Two. Three."))
    await convo.events.put(ReplyDone("One. Two. Three."))
    await _until(lambda: len(channel.of_type("tts_audio")) == 2)

    assert loader.tts.spoken == ["One.", "Three."]
    assert "listening" not in _states(channel)  # two clips are still playing
    app.handle_playback_done()
    await _settle()
    assert not app.turn_task.done()
    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)

    errors = channel.of_type("agent_error")
    assert len(errors) == 1 and "turn failed" not in errors[0]["message"]
    assert _states(channel)[-1] == "listening"


async def test_interrupting_the_reply_before_a_scene_stops_the_scene(tmp_path):  # S5, S6 (R1)
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("Let me show you. "))
    await _until(lambda: len(_reply_clips(channel)) == 1)

    scene = asyncio.create_task(convo.toolbox.present(SCENE))
    await _settle()
    assert not scene.done()  # still waiting for the sentence before it

    await app.handle_interrupt()
    app.handle_playback_done()  # the page reports the stopped sentence
    result = json.loads(await asyncio.wait_for(scene, timeout=1))

    assert result == {"status": "stopped", "step": 1, "total": 2}
    assert _scene_clips(channel) == []
    assert channel.of_type("walkthrough") == []
    assert not app.walkthrough.active
    await convo.events.put(ReplyDone("Let me show you."))
    await asyncio.wait_for(app.turn_task, timeout=2)


async def test_a_page_that_leaves_during_the_pre_scene_wait_ends_the_scene(tmp_path):  # S6
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("Let me show you. "))
    await _until(lambda: len(_reply_clips(channel)) == 1)

    scene = asyncio.create_task(convo.toolbox.present(SCENE))
    await _settle()
    channel.is_connected = False
    await app.handle_disconnect()
    result = json.loads(await asyncio.wait_for(scene, timeout=1))

    assert result["status"] == "page_disconnected"
    assert _scene_clips(channel) == []
    assert channel.of_type("walkthrough") == []
    await app.shutdown()


async def test_clips_nobody_received_do_not_extend_the_playback_wait(tmp_path):  # S3
    app, channel, loader, convo = await _live(tmp_path)
    channel.is_connected = False  # no page: nothing is delivered, nothing will be acknowledged
    text = "One. Two. Three."
    await convo.events.put(TextDelta(text))
    await convo.events.put(ReplyDone(text))

    await asyncio.wait_for(app.turn_task, timeout=1)  # not PLAYBACK_GRACE_S plus the clips' length
    assert channel.of_type("tts_audio") == []


async def _restart(app, backend, old):
    await app.handle_start("fake", "small", str(old))
    await _until(lambda: len(backend.conversations) == 2 and app._conversation is not None)
    return backend.conversations[1]


async def test_restarting_the_session_keeps_the_debt_of_clips_still_on_the_page(tmp_path):  # S5 (F3)
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("One. Two. "))
    await _until(lambda: len(_reply_clips(channel)) == 2)

    second = await _restart(app, app._backend, tmp_path)
    await app.handle_turn_text("again")
    await asyncio.sleep(0)
    await second.events.put(TextDelta("Next. "))
    await second.events.put(ReplyDone("Next."))
    await _until(lambda: len(_reply_clips(channel)) == 3)

    app.handle_playback_done()  # the page reports the two cancelled clips late
    app.handle_playback_done()
    await _settle()
    assert not app.turn_task.done()

    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)
    await app.shutdown()


async def test_a_page_that_left_owes_no_ack_debt_to_the_next_session(tmp_path):  # S5 (F3)
    app, channel, loader, convo = await _live(tmp_path)
    await convo.events.put(TextDelta("One. Two. "))
    await _until(lambda: len(_reply_clips(channel)) == 2)
    await app.handle_interrupt()
    await convo.events.put(ReplyDone("One. Two."))
    await asyncio.wait_for(app.turn_task, timeout=2)

    await app.handle_disconnect()  # that page is gone; it will never report those clips
    channel.is_connected = True

    await app.handle_turn_text("again")
    await asyncio.sleep(0)
    await convo.events.put(TextDelta("Next. "))
    await convo.events.put(ReplyDone("Next."))
    await _until(lambda: len(_reply_clips(channel)) == 3)
    app.handle_playback_done()
    await asyncio.wait_for(app.turn_task, timeout=2)
    await app.shutdown()
