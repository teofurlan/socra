"""present() inside a project session: mentor and exam play narrated scenes on the agent page."""
from __future__ import annotations

import asyncio
import json

from socra_server.domain.modes import PRESENT, get_mode
from socra_server.socra_tools import CallbackToolbox, specs_for
from tests.test_agent_mode import Convo, ModeBackend, _make, _started

CODE = "a = 1\nb = 2\nc = a + b"
SCENE = {
    "version": 1,
    "title": "Adding",
    "objects": [{"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}}],
    "steps": [{"id": "names", "say": "Two names."}, {"id": "sum", "say": "Add them."}],
    "cues": [
        {"at": "names", "do": [{"object": "src", "action": "focus", "params": {"lines": [1, 2]}}]},
        {"at": "sum", "do": [{"object": "src", "action": "focus", "params": {"lines": [3, 3]}}]},
    ],
}


async def _opened(tmp_path):
    backend = ModeBackend([Convo([])])
    app, channel, loader = _make(backend, tmp_path)
    await _started(app, tmp_path)
    return app, channel, loader, backend.opens[0]["toolbox"]


async def _play(app, channel, coro, *, ack=True):
    """Run a present() call, playing every step clip to its end like the page would."""
    task = asyncio.create_task(coro)
    if not ack:
        return task
    acked: set[int] = set()
    for _ in range(400):
        if task.done():
            break
        if ack:
            for message in channel.of_type("tts_audio"):
                seq = message.get("step", {}).get("seq")
                if seq is not None and seq not in acked:
                    acked.add(seq)
                    app.handle_playback_done(seq)
        await asyncio.sleep(0.002)
    return task


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0.002)


def test_mentor_and_exam_offer_present_and_the_agent_mode_does_not():
    assert PRESENT in get_mode("mentor").tools and PRESENT in get_mode("exam").tools
    assert PRESENT not in get_mode("agent").tools
    assert "present" in {spec.id for spec in specs_for(get_mode("mentor"))}


async def test_the_present_tool_passes_the_scene_to_the_toolbox():
    seen = []

    async def present(scene):
        seen.append(scene)
        return "played"

    async def unused(*_args):
        return ""

    toolbox = CallbackToolbox(switch=unused, record=unused, search=unused, play=present)
    spec = next(s for s in specs_for(get_mode("mentor")) if s.id == PRESENT)
    assert spec.schema["required"] == ["scene"]
    assert await spec.handler(toolbox, {"scene": SCENE}) == "played"
    assert seen == [SCENE]


async def test_a_scene_plays_on_the_agent_page_and_the_agent_hears_how_it_ended(tmp_path):
    app, channel, loader, toolbox = await _opened(tmp_path)

    task = await _play(app, channel, toolbox.present(SCENE))
    result = json.loads(await asyncio.wait_for(task, 2))

    assert result == {"status": "completed", "steps": 2}
    assert channel.of_type("walkthrough")[0]["title"] == "Adding"
    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert [c["step"]["state"]["src"]["lines"] for c in clips] == [[1, 2], [3, 3]]
    assert loader.tts.spoken == ["Two names.", "Add them."]
    assert channel.of_type("walkthrough_status")[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "completed"}


async def test_an_invalid_scene_is_returned_to_the_agent_and_nothing_plays(tmp_path):
    app, channel, loader, toolbox = await _opened(tmp_path)
    before = len(channel.sent)

    result = json.loads(await toolbox.present({"version": 1, "title": "x", "steps": [{"id": "a", "say": ""}]}))

    assert result["status"] == "invalid" and result["errors"][0]["path"] == "steps[0].say"
    assert channel.sent[before:] == []
    assert loader.tts.spoken == []


async def test_a_second_scene_while_one_plays_is_busy(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    assert json.loads(await toolbox.present(SCENE)) == {"status": "busy"}
    await app.handle_walkthrough_control("stop")
    assert json.loads(await asyncio.wait_for(task, 2))["status"] == "stopped"


async def test_the_page_controls_steer_the_scene(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    await app.handle_walkthrough_control("explode")  # ignored
    await app.handle_walkthrough_control("stop")
    assert json.loads(await asyncio.wait_for(task, 2)) == {"status": "stopped", "step": 1, "total": 2}


async def test_what_the_user_says_during_a_scene_is_a_command_not_a_turn(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()

    await app.handle_turn_text("what is a port?")
    assert channel.of_type("notice")[-1]["text"].startswith("Say or type")
    assert app.turn_task is None

    await app.handle_turn_text("stop")
    assert json.loads(await asyncio.wait_for(task, 2))["status"] == "stopped"


async def test_a_reconnected_page_catches_up_with_the_scene(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    channel.sent.clear()

    await app.handle_hello()

    assert [m["type"] for m in channel.sent if m["type"].startswith("walkthrough")] == [
        "walkthrough", "walkthrough_step", "walkthrough_status",
    ]
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)


async def test_losing_the_page_ends_the_scene(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    await app.handle_disconnect()
    assert json.loads(await asyncio.wait_for(task, 2))["status"] == "page_disconnected"


async def test_a_cancelled_scene_tells_the_page_it_ended(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert channel.of_type("walkthrough_status")[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "stopped"}
    assert not app.walkthrough.active


async def test_a_reply_clip_without_a_step_still_counts_as_the_reply_playing(tmp_path):
    app, *_ = await _opened(tmp_path)
    app.handle_playback_done()
    assert app.acknowledged_clips == 1
