"""present() inside a project session: mentor and exam play narrated scenes on the agent page."""
from __future__ import annotations

import asyncio
import base64
import json

import pytest

from socra_server.domain.agent import ReplyDone
from socra_server.domain.modes import PRESENT, get_mode
from socra_server.socra_tools import CallbackToolbox, specs_for
from tests.test_agent_app import _finish_turn, _wav
from tests.test_agent_mode import VALID, Convo, ModeBackend, _make, _started

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


def test_mentor_and_exam_offer_present():
    assert PRESENT in get_mode("mentor").tools and PRESENT in get_mode("exam").tools
    assert "present" in {spec.id for spec in specs_for(get_mode("mentor"))}


async def test_the_present_tool_passes_the_scene_to_the_toolbox():
    seen = []

    async def present(scene):
        seen.append(scene)
        return "played"

    async def unused(*_args):
        return ""

    toolbox = CallbackToolbox(switch=unused, record=unused, search=unused, play=present, clear=unused, point=unused, show=unused, replay=unused)
    spec = next(s for s in specs_for(get_mode("mentor")) if s.id == PRESENT)
    assert spec.schema["required"] == ["scene"]
    assert await spec.handler(toolbox, {"scene": SCENE}) == "played"
    assert seen == [SCENE]


async def test_a_scene_plays_on_the_agent_page_and_the_agent_hears_how_it_ended(tmp_path):
    app, channel, loader, toolbox = await _opened(tmp_path)

    task = await _play(app, channel, toolbox.present(SCENE))
    result = json.loads(await asyncio.wait_for(task, 2))

    assert result | {"note": None} == {"status": "completed", "steps": 2, "note": None}
    assert channel.of_type("walkthrough")[0]["title"] == "Adding"
    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert all("pointing" not in c["step"] for c in clips)
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


async def test_a_review_turn_during_a_scene_is_still_a_scene_command_not_a_draft(tmp_path):  # S4
    app, channel, loader, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    loader.stt.text = "stop"

    await app.handle_turn_audio(base64.b64encode(_wav(0.5)).decode(), review=True)

    assert json.loads(await asyncio.wait_for(task, 2))["status"] == "stopped"
    assert channel.of_type("transcript_draft") == []


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


async def test_clearing_an_ended_scene_tells_the_page(tmp_path):  # S4
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE))
    await asyncio.wait_for(task, 2)

    text = await toolbox.clear_scene()

    assert channel.of_type("walkthrough_cleared") == [{"type": "walkthrough_cleared"}]
    assert text == "Scene cleared."
    assert await toolbox.clear_scene() == "No finished scene is on screen."
    assert len(channel.of_type("walkthrough_cleared")) == 1


async def test_a_finished_scene_is_cleared_when_the_session_switches_to_agent(tmp_path):  # review finding
    # Agent mode has no clear_scene tool, so Socra drops the scene itself; mentor and exam can.
    backend = ModeBackend([Convo([[ReplyDone(VALID)]]), Convo([[ReplyDone("ok")]])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]
    task = await _play(app, channel, toolbox.present(SCENE))
    await asyncio.wait_for(task, 2)
    assert channel.of_type("walkthrough_cleared") == []

    await toolbox.switch_mode("agent")
    await app.handle_mode_switch_response("agent", True)
    await asyncio.wait_for(app.switch_task, timeout=3)

    assert channel.of_type("walkthrough_cleared") == [{"type": "walkthrough_cleared"}]
    assert await backend.opens[1]["toolbox"].clear_scene() == "No finished scene is on screen."


async def test_a_finished_scene_survives_a_switch_to_a_mode_that_can_clear_it(tmp_path):  # review finding
    backend = ModeBackend([Convo([[ReplyDone(VALID)]]), Convo([[ReplyDone("ok")]])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]
    task = await _play(app, channel, toolbox.present(SCENE))
    await asyncio.wait_for(task, 2)

    await toolbox.switch_mode("exam")
    await app.handle_mode_switch_response("exam", True)
    await asyncio.wait_for(app.switch_task, timeout=3)

    assert channel.of_type("walkthrough_cleared") == []


async def test_a_scene_that_still_plays_is_not_cleared(tmp_path):  # S4
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()

    assert await toolbox.clear_scene() == "No finished scene is on screen."
    assert channel.of_type("walkthrough_cleared") == []
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)


async def test_clearing_without_any_scene_sends_nothing(tmp_path):  # S4
    _, channel, _, toolbox = await _opened(tmp_path)

    assert await toolbox.clear_scene() == "No finished scene is on screen."
    assert channel.of_type("walkthrough_cleared") == []


async def test_a_new_scene_after_clearing_can_be_cleared_again(tmp_path):  # S4
    app, channel, _, toolbox = await _opened(tmp_path)
    for _ in range(2):
        await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
        assert await toolbox.clear_scene() == "Scene cleared."


async def _scene_on_screen(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    return app, channel, toolbox


async def test_valid_targets_reach_the_page_normalized(tmp_path):  # S5
    _, channel, toolbox = await _scene_on_screen(tmp_path)

    text = await toolbox.point_at([{"object": "src", "lines": (1, 2)}])

    assert channel.of_type("walkthrough_point") == [
        {"type": "walkthrough_point", "targets": [{"object": "src", "lines": [1, 2]}]}
    ]
    assert text == "Highlighted on screen."


async def test_an_empty_list_removes_the_highlight(tmp_path):  # S5
    _, channel, toolbox = await _scene_on_screen(tmp_path)

    text = await toolbox.point_at([])

    assert channel.of_type("walkthrough_point") == [{"type": "walkthrough_point", "targets": []}]
    assert "removed" in text.lower()


async def test_invalid_targets_send_nothing_and_come_back_as_errors(tmp_path):  # S5, S6
    _, channel, toolbox = await _scene_on_screen(tmp_path)

    text = await toolbox.point_at([{"object": "nope"}, {"object": "src", "lines": [3, 9]}])

    assert channel.of_type("walkthrough_point") == []
    lines = text.splitlines()
    assert lines[0].startswith("targets[0].object: ") and lines[1].startswith("targets[1].lines: ")


async def test_pointing_needs_a_finished_scene_on_screen(tmp_path):  # S5
    _, channel, _, toolbox = await _opened(tmp_path)

    assert await toolbox.point_at([{"object": "src"}]) == "No finished scene is on screen."
    assert channel.of_type("walkthrough_point") == []


async def test_after_clear_scene_pointing_reports_no_scene(tmp_path):  # S5
    _, channel, toolbox = await _scene_on_screen(tmp_path)
    await toolbox.clear_scene()

    assert await toolbox.point_at([{"object": "src"}]) == "No finished scene is on screen."
    assert channel.of_type("walkthrough_point") == []


async def test_a_scene_that_still_plays_cannot_be_pointed_at(tmp_path):  # S5
    app, channel, _, toolbox = await _opened(tmp_path)
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()

    assert await toolbox.point_at([{"object": "src"}]) == "No finished scene is on screen."
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)


async def test_pointing_is_checked_against_the_new_scene(tmp_path):  # S5
    app, channel, toolbox = await _scene_on_screen(tmp_path)
    other = SCENE | {"objects": [{"id": "other", "primitive": "code", "params": {"code": "x", "language": ""}}],
                     "cues": []}
    await asyncio.wait_for(await _play(app, channel, toolbox.present(other)), 2)

    assert (await toolbox.point_at([{"object": "src"}])).startswith("targets[0].object: ")
    assert await toolbox.point_at([{"object": "other", "lines": [1, 1]}]) == "Highlighted on screen."


async def test_losing_the_page_forgets_the_scene(tmp_path):  # S5
    app, _, toolbox = await _scene_on_screen(tmp_path)

    await app.handle_disconnect()

    assert await toolbox.point_at([]) == "No finished scene is on screen."


STRUCTURES = {
    "version": 1,
    "title": "Tables",
    "objects": [
        {"id": "ht", "primitive": "structure", "params": {"kind": "hashTable", "items": [1], "buckets": 5}},
        {"id": "tr", "primitive": "structure", "params": {"kind": "tree", "items": [5, 3]}},
        {"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}},
    ],
    "steps": [{"id": "start", "say": "A table and a tree."}],
    "cues": [],
}


async def _structures_on_screen(tmp_path):
    app, channel, _, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(STRUCTURES)), 2)
    return app, channel, toolbox


def _insert(object_id, key):
    return {"object": object_id, "op": {"action": "insert", "params": {"key": key}}}


async def test_show_result_sends_one_result_for_that_object_and_says_the_outcome(tmp_path):  # S7
    _, channel, toolbox = await _structures_on_screen(tmp_path)

    text = await toolbox.show_result(_insert("ht", 6))  # 6 % 5 == 1, where 1 already is

    sent = channel.of_type("walkthrough_result")
    assert len(sent) == 1
    assert sent[0]["type"] == "walkthrough_result" and sent[0]["object"] == "ht"
    assert sent[0]["state"]["buckets"][1] == [1, 6]
    assert sent[0]["state"]["last"]["collision"] is True
    assert "bucket 1" in text and "collision" in text and "no collision" not in text


async def test_a_later_show_result_chains_on_the_previous_one(tmp_path):  # S7
    _, channel, toolbox = await _structures_on_screen(tmp_path)

    await toolbox.show_result(_insert("ht", 6))
    await toolbox.show_result(_insert("ht", 11))

    assert channel.of_type("walkthrough_result")[-1]["state"]["buckets"][1] == [1, 6, 11]


async def test_point_at_validates_against_the_state_a_result_left(tmp_path):  # S7
    _, channel, toolbox = await _structures_on_screen(tmp_path)
    assert (await toolbox.point_at([{"object": "tr", "part": "node:4"}])).startswith("targets[0].part: ")

    await toolbox.show_result(_insert("tr", 4))

    assert await toolbox.point_at([{"object": "tr", "part": "node:4"}]) == "Highlighted on screen."


async def test_an_invalid_result_sends_nothing_and_leaves_the_state(tmp_path):  # S7
    _, channel, toolbox = await _structures_on_screen(tmp_path)

    text = await toolbox.show_result({"object": "src", "op": {"action": "insert", "params": {"key": 1}}})
    again = await toolbox.show_result(_insert("ht", 1))  # already there

    assert text.startswith("object: ") and again.startswith("op: ")
    assert channel.of_type("walkthrough_result") == []
    await toolbox.show_result(_insert("ht", 6))
    assert channel.of_type("walkthrough_result")[0]["state"]["buckets"][1] == [1, 6]


async def test_show_result_needs_a_finished_scene_on_screen(tmp_path):  # S7
    app, channel, _, toolbox = await _opened(tmp_path)
    assert await toolbox.show_result(_insert("ht", 2)) == "No finished scene is on screen."
    task = await _play(app, channel, toolbox.present(STRUCTURES), ack=False)
    await _settle()
    assert await toolbox.show_result(_insert("ht", 2)) == "No finished scene is on screen."
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)
    assert channel.of_type("walkthrough_result") == []


async def test_a_replayed_step_starts_from_the_scene_again_not_from_a_result(tmp_path):  # S7, S8
    app, channel, toolbox = await _structures_on_screen(tmp_path)
    await toolbox.show_result(_insert("ht", 6))

    await asyncio.wait_for(await _play(app, channel, toolbox.replay_step({"step": "start", "say": "Look at it fresh."})), 2)
    await toolbox.show_result(_insert("ht", 6))

    assert channel.of_type("walkthrough_result")[-1]["state"]["buckets"][1] == [1, 6]


def _replay(step, say=None, **extra):
    return {"step": step, "say": say or f"A different take on {step}.", **extra}


async def test_replay_plays_exactly_that_step_and_ends_on_it(tmp_path):  # S8
    app, channel, loader, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    channel.sent.clear()
    loader.tts.spoken.clear()

    task = await _play(app, channel, toolbox.replay_step(_replay("names", "Both variables come first.")))
    text = await asyncio.wait_for(task, 2)

    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert [c["step"]["id"] for c in clips] == ["names"]
    assert clips[0]["step"]["state"]["src"]["lines"] == [1, 2]
    assert loader.tts.spoken == ["Both variables come first."]
    assert channel.of_type("walkthrough") == []
    assert channel.of_type("walkthrough_status")[-1] == {"type": "walkthrough_status", "status": "ended", "reason": "completed"}
    assert "completed" in text.lower()
    assert await toolbox.point_at([{"object": "src", "lines": [1, 2]}]) == "Highlighted on screen."


async def test_replay_with_an_unknown_step_lists_the_valid_ids(tmp_path):  # S8
    app, channel, _, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    channel.sent.clear()

    text = await toolbox.replay_step(_replay("nope"))

    assert "names" in text and "sum" in text
    assert channel.of_type("tts_audio") == []


async def test_replay_needs_a_finished_scene_on_screen(tmp_path):  # S8
    app, channel, _, toolbox = await _opened(tmp_path)
    assert await toolbox.replay_step(_replay("names")) == "No finished scene is on screen."
    task = await _play(app, channel, toolbox.present(SCENE), ack=False)
    await _settle()
    assert await toolbox.replay_step(_replay("names")) == "No finished scene is on screen."
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)


async def test_replay_ends_when_the_page_goes_away(tmp_path):  # S8
    app, channel, _, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)

    task = await _play(app, channel, toolbox.replay_step(_replay("sum")), ack=False)
    await _settle()
    await app.handle_disconnect()

    assert "page" in (await asyncio.wait_for(task, 2)).lower()


async def test_the_user_can_stop_a_replay(tmp_path):  # S8
    app, channel, _, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)

    task = await _play(app, channel, toolbox.replay_step(_replay("sum")), ack=False)
    await _settle()
    await app.handle_walkthrough_control("stop")

    assert "stopped" in (await asyncio.wait_for(task, 2)).lower()
    assert channel.of_type("walkthrough_status")[-1]["status"] == "ended"
    assert await toolbox.point_at([]) == "Highlight removed."


async def _scene_ready(tmp_path):
    app, channel, loader, toolbox = await _opened(tmp_path)
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    channel.sent.clear()
    loader.tts.spoken.clear()
    return app, channel, loader, toolbox


async def test_replay_speaks_the_new_explanation_not_the_original(tmp_path):  # S11
    app, channel, loader, toolbox = await _scene_ready(tmp_path)

    await asyncio.wait_for(await _play(app, channel, toolbox.replay_step(_replay("sum", "  The sum needs both names.  "))), 2)

    assert loader.tts.spoken == ["The sum needs both names."]
    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert [c["step"]["say"] for c in clips] == ["The sum needs both names."]
    assert clips[0]["step"]["state"]["src"]["lines"] == [3, 3]


@pytest.mark.parametrize("say", [None, "", "   ", 7])
async def test_replay_without_a_usable_say_is_rejected_and_nothing_plays(tmp_path, say):  # S11
    app, channel, loader, toolbox = await _scene_ready(tmp_path)
    args = {"step": "sum"} if say is None else {"step": "sum", "say": say}

    text = await toolbox.replay_step(args)

    assert text.startswith("say:") and "required" in text
    assert channel.sent == [] and loader.tts.spoken == []


@pytest.mark.parametrize("say", ["Add them.", "  add THEM.  "])
async def test_replay_repeating_the_original_say_is_rejected(tmp_path, say):  # S11
    app, channel, loader, toolbox = await _scene_ready(tmp_path)

    text = await toolbox.replay_step({"step": "sum", "say": say})

    assert "differently" in text
    assert channel.sent == [] and loader.tts.spoken == []


async def test_replay_with_a_too_long_say_is_rejected(tmp_path):  # S11
    app, channel, loader, toolbox = await _scene_ready(tmp_path)

    text = await toolbox.replay_step({"step": "sum", "say": "x" * 601})

    assert "at most 600" in text
    assert channel.sent == [] and loader.tts.spoken == []


async def test_replay_with_invalid_targets_returns_errors_and_nothing_plays(tmp_path):  # S11
    app, channel, loader, toolbox = await _scene_ready(tmp_path)

    text = await toolbox.replay_step(_replay("sum", targets=[{"object": "nope"}]))

    assert text.startswith("targets[0]")
    assert channel.sent == [] and loader.tts.spoken == []
    assert "targets" in await toolbox.replay_step(_replay("sum", targets="src"))


async def test_replay_carries_the_pointing_on_its_step_and_sends_no_separate_point(tmp_path):  # S11
    app, channel, _, toolbox = await _scene_ready(tmp_path)
    target = {"object": "src", "lines": [3, 3]}

    task = await _play(app, channel, toolbox.replay_step(_replay("sum", targets=[target])))
    await asyncio.wait_for(task, 2)

    assert channel.of_type("walkthrough_point") == []
    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert len(clips) == 1
    assert clips[0]["step"]["pointing"] == [target]
    assert await toolbox.point_at([target]) == "Highlighted on screen."


async def test_replay_without_targets_sends_no_point_or_pointing(tmp_path):  # S11
    app, channel, _, toolbox = await _scene_ready(tmp_path)

    await asyncio.wait_for(await _play(app, channel, toolbox.replay_step(_replay("sum"))), 2)

    assert channel.of_type("walkthrough_point") == []
    clips = [m for m in channel.of_type("tts_audio") if "step" in m]
    assert len(clips) == 1 and "pointing" not in clips[0]["step"]


async def _scene_then_reply(tmp_path, reply):
    """A scene has ended on screen; then the agent answers a turn with `reply`."""
    backend = ModeBackend([Convo([[ReplyDone(reply)]])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    await app.handle_turn_text("show me the code")
    await _finish_turn(app, channel)
    return app, channel, toolbox


async def test_a_code_reply_makes_the_server_forget_the_ended_scene(tmp_path):  # S4
    _, channel, toolbox = await _scene_then_reply(tmp_path, "Here:\n```py\na = 1\n```")
    channel.sent.clear()

    assert await toolbox.point_at([{"object": "src"}]) == "No finished scene is on screen."
    assert await toolbox.show_result({"object": "src"}) == "No finished scene is on screen."
    assert await toolbox.replay_step(_replay("names")) == "No finished scene is on screen."
    assert await toolbox.clear_scene() == "No finished scene is on screen."
    assert channel.sent == []  # the page already dropped it: no walkthrough_cleared either


async def test_a_reply_without_code_keeps_the_ended_scene(tmp_path):  # S4
    _, channel, toolbox = await _scene_then_reply(tmp_path, "It adds two numbers.")

    assert await toolbox.point_at([{"object": "src"}]) == "Highlighted on screen."
    assert len(channel.of_type("walkthrough_point")) == 1


async def test_a_code_reply_while_a_scene_plays_does_not_forget_it(tmp_path):  # S4
    backend = ModeBackend([Convo([])])
    app, channel, _ = _make(backend, tmp_path)
    await _started(app, tmp_path)
    toolbox = backend.opens[0]["toolbox"]
    await asyncio.wait_for(await _play(app, channel, toolbox.present(SCENE)), 2)
    task = await _play(app, channel, toolbox.replay_step(_replay("names")), ack=False)
    await _settle()
    assert app.walkthrough.active

    await app._send_reply("```\ncode\n```")

    assert app._scene_on_screen is not None
    await app.handle_walkthrough_control("stop")
    await asyncio.wait_for(task, 2)
    assert app._scene_on_screen is not None


# --- predictions never alter the scene; point_at needs targets (#71) ---------------------------


async def test_show_result_leaves_the_scenes_step_states_alone_for_a_replay(tmp_path):  # S7, S8
    app, channel, toolbox = await _structures_on_screen(tmp_path)
    scene, index = app._scene_on_screen
    before = scene.state_at(index)
    await toolbox.show_result(_insert("ht", 6))
    await toolbox.show_result(_insert("tr", 4))

    assert scene.state_at(index) == before
    channel.sent.clear()
    await asyncio.wait_for(await _play(app, channel, toolbox.replay_step(_replay("start"))), 2)

    clip = [m for m in channel.of_type("tts_audio") if "step" in m][0]["step"]
    assert clip["state"]["ht"]["buckets"][1] == [1]
    assert clip["state"]["ht"] == before["ht"] and clip["state"]["tr"] == before["tr"]


async def test_show_result_does_not_change_what_a_new_present_of_the_scene_shows(tmp_path):  # S7
    app, channel, toolbox = await _structures_on_screen(tmp_path)
    await toolbox.show_result(_insert("ht", 6))
    channel.sent.clear()

    await asyncio.wait_for(await _play(app, channel, toolbox.present(STRUCTURES)), 2)

    clip = [m for m in channel.of_type("tts_audio") if "step" in m][0]["step"]
    assert clip["state"]["ht"]["buckets"][1] == [1]


async def test_a_rejected_show_result_leaves_no_partial_change(tmp_path):  # S7
    app, channel, toolbox = await _structures_on_screen(tmp_path)
    scene, index = app._scene_on_screen
    before = scene.state_at(index)

    text = await toolbox.show_result({"object": "ht", "op": {"action": "insert", "params": {}}})
    await toolbox.show_result({"object": "ht", "op": {"action": "nope"}})

    assert text.startswith("op.params")
    assert app._screen_state is None
    assert scene.state_at(index) == before
    assert channel.of_type("walkthrough_result") == []


async def test_point_at_without_targets_is_an_error_and_sends_nothing(tmp_path):  # S5
    app, channel, toolbox = await _structures_on_screen(tmp_path)
    spec = next(s for s in specs_for(get_mode("mentor")) if s.id == "point_at")

    for args in ({}, {"targets": None}):
        text = await spec.handler(toolbox, args)
        assert text.startswith("targets:")
    assert channel.of_type("walkthrough_point") == []

    assert await spec.handler(toolbox, {"targets": []}) == "Highlight removed."
    assert channel.of_type("walkthrough_point") == [{"type": "walkthrough_point", "targets": []}]


async def test_replay_step_with_null_targets_does_not_crash_and_points_at_nothing(tmp_path):  # S11
    app, channel, toolbox = await _structures_on_screen(tmp_path)

    text = await asyncio.wait_for(await _play(app, channel, toolbox.replay_step(_replay("start", targets=None))), 2)

    assert "completed" in text.lower()
    assert all("pointing" not in m["step"] for m in channel.of_type("tts_audio") if "step" in m)
