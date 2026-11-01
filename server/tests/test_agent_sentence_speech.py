"""Agent replies are spoken sentence by sentence while they stream (issue #60)."""
from __future__ import annotations

import asyncio
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

    async def open_live(model, cwd, decide, **kw):
        conversation = LiveConversation(decide)
        backend.conversations.append(conversation)
        return conversation

    backend.open = open_live
    await app.handle_start("fake", "small", str(tmp_path))
    channel.sent.clear()
    await app.handle_turn_text("explain")
    await asyncio.sleep(0)
    return app, channel, loader, backend.conversations[0]


async def _settle() -> None:
    # Synthesis runs in a worker thread: give it real time to finish.
    await asyncio.sleep(0.05)


def _states(channel) -> list[str]:
    return [m["state"] for m in channel.of_type("state")]


async def test_first_sentence_is_spoken_before_the_reply_finishes(tmp_path):  # S1
    app, channel, loader, convo = await _live(tmp_path)

    await convo.events.put(TextDelta("First sentence. Second par"))
    await _settle()

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
