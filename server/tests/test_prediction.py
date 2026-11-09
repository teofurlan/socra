"""Prediction results (#71, S7): the real outcome of one operation on what is on screen."""
from __future__ import annotations

from socra_server.domain.prediction import predict
from socra_server.domain.scene import parse_scene

CODE = "a = 1"


def _scene(*, cues=None):
    scene, errors = parse_scene({
        "version": 1, "title": "T",
        "objects": [
            {"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}},
            {"id": "arr", "primitive": "structure", "params": {"kind": "array", "items": [4, 5, 6]}},
            {"id": "hash", "primitive": "structure", "params": {"kind": "hashTable", "items": [1], "buckets": 5}},
            {"id": "tree", "primitive": "structure", "params": {"kind": "tree", "items": [5, 3, 8]}},
            {"id": "later", "primitive": "structure", "hidden": True, "params": {"kind": "stack", "items": []}},
        ],
        "steps": [{"id": "s1", "say": "One."}],
        "cues": cues or [],
    })
    assert scene is not None, errors
    return scene


def _op(action, **params):
    return {"action": action, "params": params}


def _predict(object_id, op, state=None):
    scene = _scene()
    return predict(scene, state or scene.state_at(0), {"object": object_id, "op": op})


def test_an_array_set_returns_the_new_state_and_what_it_did():
    result, errors = _predict("arr", _op("set", index=1, value=9))
    assert errors == []
    assert result.object == "arr"
    assert result.state["items"] == [4, 9, 6]
    assert result.state["last"] == {"op": "set", "index": 1, "value": 9, "previous": 5}
    assert "9" in result.outcome and "5" in result.outcome


def test_a_hash_insert_into_a_free_bucket_says_where_it_landed():
    result, errors = _predict("hash", _op("insert", key=3))
    assert errors == []
    assert result.state["last"]["bucket"] == 3 and result.state["last"]["collision"] is False
    assert "bucket 3" in result.outcome and "no collision" in result.outcome


def test_a_hash_insert_that_collides_says_so():
    result, errors = _predict("hash", _op("insert", key=6))  # 6 % 5 == 1, where 1 already is
    assert errors == []
    assert result.state["last"]["collision"] is True
    assert "bucket 1" in result.outcome and "collision" in result.outcome and "no collision" not in result.outcome


def test_a_tree_insert_reports_the_path():
    result, errors = _predict("tree", _op("insert", key=4))
    assert errors == []
    assert result.state["last"]["path"] == [5, 3, 4]
    assert "5" in result.outcome and "3" in result.outcome and "4" in result.outcome


def test_a_lookup_that_finds_nothing_says_not_found():
    result, _ = _predict("tree", _op("lookup", key=7))
    assert "not found" in result.outcome


def test_applying_twice_chains_on_the_previous_result():
    scene = _scene()
    first, _ = predict(scene, scene.state_at(0), {"object": "hash", "op": _op("insert", key=3)})
    shown = scene.state_at(0) | {"hash": first.state}
    second, errors = predict(scene, shown, {"object": "hash", "op": _op("insert", key=8)})  # 8 % 5 == 3
    assert errors == []
    assert second.state["buckets"][3] == [3, 8]
    assert second.state["last"]["collision"] is True


def test_the_input_state_is_not_changed():
    scene = _scene()
    before = scene.state_at(0)
    predict(scene, before, {"object": "arr", "op": _op("set", index=0, value=1)})
    assert before == scene.state_at(0)


def test_errors_come_back_as_path_message_lines():
    cases = [
        ({"object": "nope", "op": _op("peek")}, "object: "),
        ({"object": "src", "op": _op("peek")}, "object: "),
        ({"object": "later", "op": _op("push", value=1)}, "object: "),
        ({"object": "arr", "op": _op("insert", key=1)}, "op.action: "),
        ({"object": "arr", "op": _op("clear")}, "op.action: "),
        ({"object": "arr", "op": _op("set", index=9, value=1)}, "op: "),
        ({"object": "arr", "op": _op("set", index="x", value=1)}, "op.params.index: "),
        ({"object": "arr", "op": "set"}, "op: "),
        ({"object": "arr"}, "op: "),
        ({"object": "arr", "op": _op("set", index=0, value=1), "extra": 1}, "extra: "),
        ({"object": "arr", "op": {"action": "set", "params": {"index": 0, "value": 1}, "x": 1}}, "op.x: "),
        ("insert", "args: "),
    ]
    scene = _scene()
    for raw, prefix in cases:
        result, errors = predict(scene, scene.state_at(0), raw)
        assert result is None and errors, raw
        assert all(e.startswith(prefix) for e in errors), (raw, errors)


def test_unknown_object_lists_the_structures():
    result, errors = _predict("nope", _op("peek"))
    assert result is None and "arr" in errors[0] and "hash" in errors[0]
