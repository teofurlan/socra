"""Pointing at objects of the finished scene (#71, S5 and S6): a pure check of the targets."""
from __future__ import annotations

from socra_server.domain.pointing import validate_targets
from socra_server.domain.scene import parse_scene

CODE = "a = 1\nb = 2\nc = a + b"


def _scene(*extra, steps=None, cues=None):
    objects = [
        {"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}},
        {"id": "flow", "primitive": "diagram", "params": {
            "nodes": [{"id": "api", "label": "API"}, {"id": "db", "label": "DB"}],
            "edges": [{"from": "api", "to": "db"}],
        }},
        {"id": "arr", "primitive": "structure", "params": {"kind": "array", "items": [4, 5, 6]}},
        {"id": "hash", "primitive": "structure", "params": {"kind": "hashTable", "items": [1, 6], "buckets": 5}},
        {"id": "tree", "primitive": "structure", "params": {"kind": "tree", "items": [5, 3, 8]}},
        {"id": "box", "primitive": "shape", "params": {"shape": "cube"}},
        *extra,
    ]
    scene, errors = parse_scene({
        "version": 1, "title": "T", "objects": objects,
        "steps": steps or [{"id": "s1", "say": "One."}],
        "cues": cues or [],
    })
    assert scene is not None, errors
    return scene


def _check(raw, scene=None, index=None):
    scene = scene or _scene()
    return validate_targets(scene, len(scene.steps) - 1 if index is None else index, raw)


def test_a_bare_object_is_a_valid_target():
    targets, errors = _check([{"object": "flow"}])
    assert errors == [] and targets == [{"object": "flow"}]


def test_an_empty_list_removes_the_highlight():
    assert _check([]) == ([], [])


def test_a_diagram_node_is_a_valid_part():
    targets, errors = _check([{"object": "flow", "part": "db"}])
    assert errors == [] and targets == [{"object": "flow", "part": "db"}]


def test_a_diagram_part_must_be_a_node_id():
    _, errors = _check([{"object": "flow", "part": "cache"}])
    assert errors and errors[0].startswith("targets[0].part: ") and "cache" in errors[0]


def test_structure_parts_that_exist_are_valid():
    parts = [("arr", "cell:0"), ("arr", "cell:2"), ("hash", "bucket:4"), ("hash", "entry:1:0"),
             ("hash", "entry:1:1"), ("tree", "node:5"), ("tree", "node:8")]
    for obj, part in parts:
        targets, errors = _check([{"object": obj, "part": part}])
        assert errors == [] and targets == [{"object": obj, "part": part}], (obj, part)


def test_structure_parts_that_do_not_exist_are_rejected():
    bad = [("arr", "cell:3"), ("arr", "cell:-1"), ("arr", "cell:x"), ("arr", "bucket:0"), ("hash", "bucket:5"),
           ("hash", "entry:1:2"), ("hash", "entry:0:0"), ("hash", "cell:0"), ("tree", "node:7"),
           ("tree", "node:x"), ("tree", "cell:0"), ("arr", "bogus")]
    for obj, part in bad:
        targets, errors = _check([{"object": obj, "part": part}])
        assert targets == [] and len(errors) == 1 and errors[0].startswith("targets[0].part: "), (obj, part)


def test_parts_follow_the_last_state_of_the_scene():
    scene = _scene(
        steps=[{"id": "s1", "say": "One."}, {"id": "s2", "say": "Two."}],
        cues=[{"at": "s2", "do": [{"object": "hash", "action": "insert", "params": {"key": 2}}]}],
    )
    assert _check([{"object": "hash", "part": "entry:2:0"}], scene)[1] == []
    assert _check([{"object": "hash", "part": "entry:2:0"}], scene, index=0)[1] != []


def test_code_lines_are_a_valid_range():
    targets, errors = _check([{"object": "src", "lines": [2, 3]}])
    assert errors == [] and targets == [{"object": "src", "lines": [2, 3]}]


def test_code_lines_out_of_range_or_reversed_are_rejected():
    for lines in ([0, 1], [3, 2], [1, 4], [1], "1-2", [1.5, 2], [True, 2]):
        targets, errors = _check([{"object": "src", "lines": lines}])
        assert targets == [] and len(errors) == 1 and errors[0].startswith("targets[0].lines: "), lines


def test_lines_only_apply_to_code_and_parts_not_to_code():
    assert _check([{"object": "flow", "lines": [1, 1]}])[1][0].startswith("targets[0].lines: ")
    assert _check([{"object": "src", "part": "x"}])[1][0].startswith("targets[0].part: ")


def test_shapes_and_headlines_cannot_be_pointed_at():
    headline = {"id": "big", "primitive": "headline", "params": {"text": "Idea"}}
    for name in ("box", "big"):
        targets, errors = _check([{"object": name}], scene=_scene(headline))
        assert targets == [] and len(errors) == 1
        assert errors[0].startswith("targets[0].object: ") and "cannot be highlighted" in errors[0]


def test_an_unknown_object_is_rejected_naming_the_known_ones():
    _, errors = _check([{"object": "nope"}])
    assert errors[0].startswith("targets[0].object: ") and "src" in errors[0]


def test_an_object_hidden_in_the_last_state_is_rejected():
    scene = _scene(
        steps=[{"id": "s1", "say": "One."}, {"id": "s2", "say": "Two."}],
        cues=[{"at": "s2", "do": [{"object": "flow", "action": "hide"}]}],
    )
    assert _check([{"object": "flow"}], scene)[1][0].startswith("targets[0].object: ")
    assert _check([{"object": "flow"}], scene, index=0)[1] == []


def test_every_problem_is_reported_with_its_path():
    _, errors = _check([{"object": "nope"}, {"object": "src", "lines": [9, 9]}, {"object": "flow"}])
    assert [e.split(":")[0] for e in errors] == ["targets[0].object", "targets[1].lines"]


def test_the_shape_of_the_arguments_is_checked():
    assert _check(None)[1][0].startswith("targets: ")
    assert _check({"object": "box"})[1][0].startswith("targets: ")
    assert _check(["box"])[1][0].startswith("targets[0]: ")
    assert _check([{"object": "box", "color": "red"}])[1][0].startswith("targets[0]: ")
    assert _check([{"part": "x"}])[1][0].startswith("targets[0].object: ")
    assert _check([{"object": "box"}] * 7)[1][0].startswith("targets: ")
