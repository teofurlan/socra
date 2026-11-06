"""The structure primitive in a scene: params, validation by simulation, per-step state, docs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from socra_server.domain.scene import PRIMITIVES, SCENE_GUIDE, parse_scene

DOCS = Path(__file__).resolve().parents[1] / "docs"


def paths(errors: list[dict]) -> list[str]:
    return [e["path"] for e in errors]


def scene_with(kind: str, params: dict, cues: list[tuple[str, list[dict]]], steps: int = 4) -> dict:
    return {
        "version": 1,
        "title": "A structure",
        "objects": [{"id": "ds", "primitive": "structure", "params": {"kind": kind} | params}],
        "steps": [{"id": f"s{i}", "say": f"Step {i}."} for i in range(steps)],
        "cues": [{"at": at, "do": [{"object": "ds"} | a for a in actions]} for at, actions in cues],
    }


def stack_scene() -> dict:
    return scene_with("stack", {"items": [1]}, [
        ("s0", [{"action": "push", "params": {"value": 2}}]),
        ("s1", [{"action": "push", "params": {"value": 3}}]),
        ("s2", [{"action": "pop"}]),
        ("s3", [{"action": "peek"}]),
    ])


def ds_state(scene, step):
    return scene.state_at(step)["ds"]


def test_a_valid_structure_scene_has_per_step_state():
    scene, errors = parse_scene(stack_scene())
    assert errors == [] and scene is not None
    assert ds_state(scene, 0) == {
        "visible": True, "kind": "stack", "items": [1, 2],
        "last": {"op": "push", "index": 1, "value": 2},
    }
    assert ds_state(scene, 1)["items"] == [1, 2, 3]
    assert ds_state(scene, 2)["items"] == [1, 2]
    assert ds_state(scene, 2)["last"] == {"op": "pop", "index": 2, "value": 3}
    assert ds_state(scene, 3)["last"]["op"] == "peek"


def test_going_back_restores_the_earlier_structure():
    scene, _ = parse_scene(stack_scene())
    first = ds_state(scene, 1)
    assert ds_state(scene, 3) != first
    assert ds_state(scene, 1) == first
    first["items"].append(99)
    assert ds_state(scene, 1)["items"] == [1, 2, 3]


def test_the_page_receives_normalized_params_with_the_initial_state():
    scene, _ = parse_scene(stack_scene())
    params = scene.objects_for_page()[0]["params"]
    assert params["kind"] == "stack" and params["items"] == [1]
    assert params["initial"] == {"kind": "stack", "items": [1], "last": None}


def test_a_hash_table_gets_its_defaults_and_shows_the_collision_it_computed():
    raw = scene_with("hashTable", {"items": [12, 7]}, [("s0", [{"action": "insert", "params": {"key": 17}}])])
    scene, errors = parse_scene(raw)
    assert errors == []
    params = scene.objects_for_page()[0]["params"]
    assert params["buckets"] == 5 and params["hash"] == "mod"
    state = ds_state(scene, 0)
    assert state["buckets"][2] == [12, 7, 17]
    assert state["last"]["collision"] is True and state["last"]["bucket"] == 2


def test_a_tree_state_carries_the_positions_the_runtime_computed():
    raw = scene_with("tree", {"items": [8, 3]}, [("s0", [{"action": "insert", "params": {"key": 10}}])])
    scene, errors = parse_scene(raw)
    assert errors == []
    nodes = {n["key"]: (n["depth"], n["slot"]) for n in ds_state(scene, 0)["nodes"]}
    assert nodes == {3: (1, 0), 8: (0, 1), 10: (1, 2)}


def test_every_kind_runs_its_operations_in_one_scene():
    scene, errors = parse_scene({
        "version": 1, "title": "All",
        "objects": [
            {"id": "a", "primitive": "structure", "params": {"kind": "array", "items": [3, 1, 2]}},
            {"id": "q", "primitive": "structure", "params": {"kind": "queue"}},
            {"id": "h", "primitive": "structure", "params": {"kind": "hashTable", "buckets": 3, "hash": "charSum", "items": ["cat"]}},
            {"id": "t", "primitive": "structure", "params": {"kind": "tree", "items": [5]}},
        ],
        "steps": [{"id": "x", "say": "Go."}],
        "cues": [{"at": "x", "do": [
            {"object": "a", "action": "swap", "params": {"indexes": [0, 1]}},
            {"object": "q", "action": "enqueue", "params": {"value": "job"}},
            {"object": "h", "action": "lookup", "params": {"key": "cat"}},
            {"object": "t", "action": "highlight", "params": {"key": 5}},
        ]}],
    })
    assert errors == []
    state = scene.state_at(0)
    assert state["a"]["items"] == [1, 3, 2] and state["q"]["items"] == ["job"]
    assert state["h"]["last"]["found"] is True and state["t"]["last"]["path"] == [5]


def test_show_and_hide_toggle_a_structure():
    raw = stack_scene()
    raw["objects"][0]["hidden"] = True
    raw["cues"][1]["do"].append({"object": "ds", "action": "show"})
    scene, errors = parse_scene(raw)
    assert errors == []
    assert ds_state(scene, 0)["visible"] is False and ds_state(scene, 1)["visible"] is True


def test_clear_drops_the_last_operation_but_keeps_the_contents():
    raw = stack_scene()
    raw["cues"][3]["do"] = [{"object": "ds", "action": "clear"}]
    scene, errors = parse_scene(raw)
    assert errors == []
    assert ds_state(scene, 3)["last"] is None and ds_state(scene, 3)["items"] == [1, 2]


# ---------------------------------------------------------------------------
# Validation simulates every cue (S5, S8)
# ---------------------------------------------------------------------------

def test_popping_an_empty_stack_is_rejected_before_anything_is_spoken():
    raw = scene_with("stack", {}, [("s1", [{"action": "pop"}])])
    scene, errors = parse_scene(raw)
    assert scene is None
    assert errors == [{"path": "cues[0].do[0]", "message": "step 's1': cannot pop an empty stack"}]


def test_the_simulation_follows_step_order_not_cue_order():
    # Listed pop first, but the push is spoken first: valid. Reversed in the story it is not.
    ok = scene_with("stack", {}, [("s1", [{"action": "pop"}]), ("s0", [{"action": "push", "params": {"value": 1}}])])
    assert parse_scene(ok)[1] == []
    bad = scene_with("stack", {}, [("s0", [{"action": "pop"}]), ("s1", [{"action": "push", "params": {"value": 1}}])])
    scene, errors = parse_scene(bad)
    assert scene is None and paths(errors) == ["cues[0].do[0]"]


def test_an_earlier_cue_can_make_a_later_operation_impossible_and_each_problem_is_reported():
    raw = scene_with("queue", {"items": [1]}, [
        ("s0", [{"action": "dequeue"}]),
        ("s1", [{"action": "dequeue"}]),
        ("s2", [{"action": "peek"}]),
    ])
    scene, errors = parse_scene(raw)
    assert scene is None
    assert paths(errors) == ["cues[1].do[0]"]  # one problem per object: what follows depends on the failed op
    assert "cannot dequeue from an empty queue" in errors[0]["message"]


def test_problems_in_different_objects_are_all_reported():
    raw = scene_with("stack", {}, [("s0", [{"action": "pop"}])])
    raw["objects"].append({"id": "q", "primitive": "structure", "params": {"kind": "queue"}})
    raw["cues"][0]["do"].append({"object": "q", "action": "dequeue"})
    scene, errors = parse_scene(raw)
    assert scene is None and paths(errors) == ["cues[0].do[0]", "cues[0].do[1]"]


@pytest.mark.parametrize(
    ("kind", "params", "action", "args", "fragment"),
    [
        ("array", {"items": [1, 2]}, "set", {"index": 2, "value": 1}, "index 2 is outside the array"),
        ("array", {"items": [1, 2]}, "swap", {"indexes": [0, 4]}, "index 4 is outside the array"),
        ("stack", {"items": list(range(10))}, "push", {"value": 1}, "the stack is full"),
        ("hashTable", {}, "remove", {"key": 3}, "key 3 is not in the hash table"),
        ("hashTable", {"items": [3]}, "insert", {"key": 3}, "already in the hash table"),
        ("tree", {"items": [4]}, "highlight", {"key": 9}, "key 9 is not in the tree"),
        ("tree", {"items": [1, 2, 3, 4, 5]}, "insert", {"key": 6}, "more than 5 levels"),
    ],
)
def test_impossible_operations_are_rejected_with_the_actions_path(kind, params, action, args, fragment):
    scene, errors = parse_scene(scene_with(kind, params, [("s2", [{"action": action, "params": args}])]))
    assert scene is None
    assert errors[0]["path"] == "cues[0].do[0]"
    assert fragment in errors[0]["message"] and "step 's2'" in errors[0]["message"]


def test_looking_up_a_missing_key_is_a_result_not_an_error():
    for kind, items, key in (("hashTable", [1], 6), ("tree", [5], 9)):
        raw = scene_with(kind, {"items": items}, [("s0", [{"action": "lookup", "params": {"key": key}}])])
        scene, errors = parse_scene(raw)
        assert errors == [] and ds_state(scene, 0)["last"]["found"] is False


# ---------------------------------------------------------------------------
# Params and action shapes
# ---------------------------------------------------------------------------

def params_problem(kind, params):
    scene, errors = parse_scene(scene_with(kind, params, []))
    assert scene is None
    return errors


@pytest.mark.parametrize(
    ("kind", "params", "path", "fragment"),
    [
        ("graph", {}, "objects[0].params.kind", "kind must be one of array, stack, queue, hashTable, tree"),
        ("array", {}, "objects[0].params.items", "an array needs at least one item"),
        ("array", {"items": "abc"}, "objects[0].params.items", "items must be a list"),
        ("array", {"items": list(range(13))}, "objects[0].params.items", "at most 12"),
        ("stack", {"items": [1.5]}, "objects[0].params.items[0]", "whole number or text"),
        ("stack", {"items": ["x" * 9]}, "objects[0].params.items[0]", "at most 8 characters"),
        ("stack", {"extra": 1}, "objects[0].params.extra", "unknown field"),
        ("stack", {"buckets": 3}, "objects[0].params.buckets", "only applies to a hashTable"),
        ("queue", {"hash": "mod"}, "objects[0].params.hash", "only applies to a hashTable"),
        ("hashTable", {"buckets": 1}, "objects[0].params.buckets", "buckets must be a whole number from 2 to 8"),
        ("hashTable", {"buckets": 9}, "objects[0].params.buckets", "from 2 to 8"),
        ("hashTable", {"buckets": "3"}, "objects[0].params.buckets", "from 2 to 8"),
        ("hashTable", {"hash": "md5"}, "objects[0].params.hash", "hash must be one of mod, charSum"),
        ("hashTable", {"items": ["a"]}, "objects[0].params.items", "mod rule needs whole-number keys"),
        ("hashTable", {"items": [1, 1]}, "objects[0].params.items", "already in the hash table"),
        ("tree", {"items": ["a"]}, "objects[0].params.items", "tree keys must be whole numbers"),
        ("tree", {"items": [1, 1]}, "objects[0].params.items", "already in the tree"),
    ],
)
def test_each_structure_param_problem_is_reported_with_its_path(kind, params, path, fragment):
    errors = params_problem(kind, params)
    assert path in paths(errors), errors
    assert fragment in next(e["message"] for e in errors if e["path"] == path)


def test_params_must_be_an_object_and_the_kind_is_required():
    raw = scene_with("stack", {}, [])
    raw["objects"][0]["params"] = "stack"
    assert "objects[0].params" in paths(parse_scene(raw)[1])
    raw["objects"][0]["params"] = {}
    assert "objects[0].params.kind" in paths(parse_scene(raw)[1])


def action_problem(kind, params, action, args):
    scene, errors = parse_scene(scene_with(kind, params, [("s0", [{"action": action} | ({"params": args} if args is not None else {})])]))
    assert scene is None
    return errors


@pytest.mark.parametrize(
    ("kind", "params", "action", "args", "path", "fragment"),
    [
        ("stack", {}, "push", None, "cues[0].do[0].params", "push needs params.value"),
        ("stack", {}, "push", {"value": 1.5}, "cues[0].do[0].params.value", "whole number or text"),
        ("stack", {}, "push", {"value": 1, "x": 2}, "cues[0].do[0].params.x", "unknown field"),
        ("stack", {}, "pop", {"x": 1}, "cues[0].do[0].params", "pop takes no params"),
        ("queue", {}, "enqueue", {"value": ""}, "cues[0].do[0].params.value", "must not be blank"),
        ("array", {"items": [1]}, "set", {"index": "0", "value": 1}, "cues[0].do[0].params.index", "index must be a whole number"),
        ("array", {"items": [1]}, "swap", {"indexes": [0]}, "cues[0].do[0].params.indexes", "two whole numbers"),
        ("array", {"items": [1]}, "highlight", {"indexes": []}, "cues[0].do[0].params.indexes", "1 to 12"),
        ("array", {"items": [1]}, "highlight", {"indexes": [0, 0]}, "cues[0].do[0].params.indexes", "must not repeat"),
        ("hashTable", {}, "insert", {"key": "a"}, "cues[0].do[0].params.key", "mod rule needs whole-number keys"),
        ("hashTable", {"hash": "charSum"}, "insert", {"key": 4}, "cues[0].do[0].params.key", "charSum rule needs text keys"),
        ("tree", {}, "insert", {}, "cues[0].do[0].params.key", "tree keys must be whole numbers"),
        ("tree", {}, "highlight", {"indexes": [0]}, "cues[0].do[0].params.indexes", "unknown field"),
    ],
)
def test_each_structure_action_problem_is_reported_with_its_path(kind, params, action, args, path, fragment):
    errors = action_problem(kind, params, action, args)
    assert path in paths(errors), errors
    assert fragment in next(e["message"] for e in errors if e["path"] == path)


def test_an_action_of_another_kind_lists_what_the_kind_supports():
    errors = action_problem("stack", {}, "enqueue", {"value": 1})
    message = next(e["message"] for e in errors if e["path"] == "cues[0].do[0].action")
    for name in ("show", "hide", "push", "pop", "peek", "clear"):
        assert name in message
    assert "enqueue" in message  # as the name it got
    assert "dequeue" not in message


def test_a_scene_with_bad_params_is_not_simulated():
    raw = scene_with("stack", {"items": [1.5]}, [("s0", [{"action": "pop"}])])
    scene, errors = parse_scene(raw)
    assert scene is None and paths(errors) == ["objects[0].params.items[0]"]


# ---------------------------------------------------------------------------
# Docs, schema, guide
# ---------------------------------------------------------------------------

EXAMPLES = ("scene.structure.example.json",)


@pytest.mark.parametrize("name", EXAMPLES)
def test_the_structure_example_scene_is_valid_and_uses_every_kind(name):
    content = json.loads((DOCS / name).read_text(encoding="utf-8"))
    scene, errors = parse_scene(content)
    assert errors == [] and scene is not None
    assert {o.params["kind"] for o in scene.objects} == {"array", "stack", "queue", "hashTable", "tree"}
    last = [scene.state_at(n)[o.id]["last"] for n in range(len(scene.steps)) for o in scene.objects]
    assert any(item and item.get("collision") for item in last)  # the hash table shows a collision


def test_the_json_schema_describes_the_structure():
    schema = json.loads((DOCS / "scene.schema.json").read_text(encoding="utf-8"))
    assert set(schema["properties"]["objects"]["items"]["properties"]["primitive"]["enum"]) == set(PRIMITIVES)
    params = schema["$defs"]["structureParams"]
    assert params["required"] == ["kind"]
    assert params["properties"]["kind"]["enum"] == ["array", "stack", "queue", "hashTable", "tree"]
    assert params["properties"]["buckets"] == {"type": "integer", "minimum": 2, "maximum": 8, "default": 5}
    assert params["properties"]["hash"]["enum"] == ["mod", "charSum"]
    actions = schema["$defs"]["action"]["properties"]["action"]["enum"]
    for name in ("set", "swap", "compare", "push", "pop", "peek", "enqueue", "dequeue", "insert", "lookup", "remove"):
        assert name in actions


def test_the_scene_guide_tells_when_to_use_a_structure_and_when_a_diagram():
    guide = SCENE_GUIDE.lower()
    assert 'primitive "structure"' in guide
    for kind in ("array", "stack", "queue", "hashtable", "tree"):
        assert kind in guide
    for op in ("swap", "compare", "push", "pop", "peek", "enqueue", "dequeue", "insert", "lookup", "remove"):
        assert op in guide
    assert "never compute" in guide  # the runtime computes bucket indexes, positions and results
    assert "not for general graphs" in guide or "not a general graph" in guide
