"""WalkthroughRunner: step playback, pause and commands, with a scripted page."""
from __future__ import annotations

import asyncio

import pytest

from socra_server.domain.walkthrough import parse_walkthrough
from socra_server.walkthrough import WalkthroughRunner
from tests.conftest import make_wav_bytes

CODE = "a = 1\nb = 2\nc = a + b\nprint(c)"


def make_walkthrough(count: int = 3):
    steps = [{"say": f"Step {i}.", "focus": {"lines": [i, i]}} for i in range(1, count + 1)]
    walkthrough, errors = parse_walkthrough(CODE, "python", steps)
    assert not errors
    return walkthrough


class Page:
    """Records what the runner sends; plays each clip to the end unless held."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.states: list[str] = []
        self.connected = True
        self.hold = False
        self.runner: WalkthroughRunner | None = None
        self.spoken: list[str] = []

    async def send(self, message: dict) -> None:
        self.messages.append(message)
        if message["type"] == "tts_audio" and not self.hold:
            seq = message["step"]["seq"]
            asyncio.get_running_loop().call_soon(self.runner.handle_playback_done, seq)

    async def set_state(self, state: str) -> None:
        self.states.append(state)

    def synthesize(self, text: str) -> bytes:
        self.spoken.append(text)
        return make_wav_bytes()

    def steps_heard(self) -> list[int]:
        return [m["step"]["index"] for m in self.messages if m["type"] == "tts_audio"]

    def statuses(self) -> list[str]:
        return [m["status"] for m in self.messages if m["type"] == "walkthrough_status"]


def make_runner(page: Page) -> WalkthroughRunner:
    runner = WalkthroughRunner(
        synthesize=page.synthesize,
        wav_duration=lambda wav: 0.01,
        send=page.send,
        set_state=page.set_state,
        is_connected=lambda: page.connected,
    )
    page.runner = runner
    return runner


async def settle(times: int = 6) -> None:
    for _ in range(times):
        await asyncio.sleep(0)
        await asyncio.sleep(0.005)


@pytest.mark.asyncio
async def test_each_step_is_spoken_separately_with_its_focus_on_the_audio():
    page = Page()
    runner = make_runner(page)

    result = await runner.run(make_walkthrough(3))

    assert result == {"status": "completed", "steps": 3}
    assert page.spoken == ["Step 1.", "Step 2.", "Step 3."]
    assert page.messages[0] == {"type": "walkthrough", "code": CODE, "language": "python", "total": 3}
    clips = [m for m in page.messages if m["type"] == "tts_audio"]
    assert [c["step"]["lines"] for c in clips] == [[1, 1], [2, 2], [3, 3]]
    assert [c["step"]["index"] for c in clips] == [1, 2, 3]
    assert clips[0]["step"]["say"] == "Step 1." and clips[0]["step"]["total"] == 3
    assert clips[0]["format"] == "wav" and clips[0]["data"]
    assert len({c["step"]["seq"] for c in clips}) == 3
    assert page.messages[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "completed"}
    assert page.states[0] == "speaking" and page.states[-1] == "idle"
    assert not runner.active


@pytest.mark.asyncio
async def test_a_step_without_focus_sends_no_lines():
    page = Page()
    runner = make_runner(page)
    walkthrough, _ = parse_walkthrough(CODE, "", [{"say": "Overview."}])
    await runner.run(walkthrough)
    clip = next(m for m in page.messages if m["type"] == "tts_audio")
    assert clip["step"]["lines"] is None


@pytest.mark.asyncio
async def test_pause_opens_listening_and_repeat_replays_the_same_step():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(2)))
    await settle()
    assert page.steps_heard() == [1]

    runner.command("pause")
    await settle()
    assert runner.paused
    assert page.statuses()[-1] == "paused" and page.states[-1] == "listening"

    page.hold = False
    runner.command("repeat")
    result = await asyncio.wait_for(task, 2)

    assert page.steps_heard() == [1, 1, 2]
    assert result == {"status": "completed", "steps": 2}
    assert "playing" in page.statuses()


@pytest.mark.asyncio
async def test_back_goes_to_the_previous_step_and_next_skips_one():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(3)))
    await settle()
    runner.command("next")
    await settle()
    runner.command("back")
    await settle()
    runner.command("next")
    await settle()
    runner.command("next")
    await settle()
    page.hold = False
    runner.command("repeat")
    result = await asyncio.wait_for(task, 2)
    assert page.steps_heard() == [1, 2, 1, 2, 3, 3]
    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_stop_ends_the_walkthrough_and_reports_where():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(3)))
    await settle()
    runner.command("next")
    await settle()
    runner.command("stop")
    result = await asyncio.wait_for(task, 2)
    assert result == {"status": "stopped", "step": 2, "total": 3}
    assert page.messages[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "stopped"}
    assert page.states[-1] == "idle"


@pytest.mark.asyncio
async def test_playback_done_for_a_stopped_clip_cannot_finish_the_next_step():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(2)))
    await settle()
    first_seq = page.messages[2]["step"]["seq"]
    runner.command("next")
    await settle()
    assert page.steps_heard() == [1, 2]

    runner.handle_playback_done(first_seq)  # stale: the page stopped clip 1
    await settle()
    assert not task.done()

    runner.handle_playback_done(page.messages[-1]["step"]["seq"])
    assert (await asyncio.wait_for(task, 2))["status"] == "completed"


@pytest.mark.asyncio
async def test_a_second_walkthrough_is_refused_while_one_is_active():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(2)))
    await settle()
    assert await runner.run(make_walkthrough(2)) == {"status": "busy"}
    runner.command("stop")
    await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_losing_the_page_ends_the_walkthrough_even_while_paused():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(3)))
    await settle()
    runner.command("pause")
    await settle()
    page.connected = False
    runner.abort()
    result = await asyncio.wait_for(task, 2)
    assert result == {"status": "page_disconnected", "step": 1, "total": 3}
    assert not runner.active


@pytest.mark.asyncio
async def test_snapshot_lets_a_reconnected_page_catch_up():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    assert runner.snapshot() == []
    task = asyncio.create_task(runner.run(make_walkthrough(2)))
    await settle()
    runner.command("pause")
    await settle()
    snapshot = runner.snapshot()
    assert [m["type"] for m in snapshot] == ["walkthrough", "walkthrough_step", "walkthrough_status"]
    assert snapshot[1]["index"] == 1 and snapshot[1]["lines"] == [1, 1]
    assert snapshot[2]["status"] == "paused"
    runner.command("stop")
    await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_losing_the_page_still_ends_the_walkthrough_cleanly_for_a_returning_page():
    page = Page()
    page.hold = True
    runner = make_runner(page)
    task = asyncio.create_task(runner.run(make_walkthrough(2)))
    await settle()
    page.connected = False
    runner.abort()
    await asyncio.wait_for(task, 2)
    assert page.messages[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "disconnected"}
    assert page.states[-1] == "idle"


@pytest.mark.asyncio
async def test_a_synthesis_failure_ends_the_walkthrough_and_reports_it():
    page = Page()
    runner = make_runner(page)

    def broken(text: str) -> bytes:
        raise RuntimeError("voice model missing")

    runner._synthesize = broken
    result = await runner.run(make_walkthrough(2))

    assert result["status"] == "error" and result["step"] == 1 and "voice model missing" in result["message"]
    assert page.messages[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "error"}
    assert page.states[-1] == "idle"
    assert not runner.active
