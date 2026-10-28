"""Pure scene rules: contract validation, per-step visual state, explain() as a scene."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from socra_server.domain.scene import (
    MAX_ACTIONS_PER_CUE,
    MAX_OBJECTS,
    MAX_STEPS,
    PRIMITIVES,
    parse_scene,
    scene_from_walkthrough,
)
from socra_server.domain.walkthrough import parse_walkthrough

DOCS = Path(__file__).resolve().parents[1] / "docs"
CODE = "a = 1\nb = 2\nc = a + b\nprint(c)"


def valid_scene() -> dict:
    return {
        "version": 1,
        "title": "Adding two numbers",
        "objects": [{"id": "src", "primitive": "code", "params": {"code": CODE, "language": "python"}}],
        "steps": [
            {"id": "intro", "say": "Two names hold numbers."},
            {"id": "sum", "say": "Then we add them."},
            {"id": "out", "say": "And print the result."},
        ],
        "cues": [
            {"at": "intro", "do": [{"object": "src", "action": "focus", "params": {"lines": [1, 2]}}]},
            {"at": "sum", "do": [{"object": "src", "action": "focus", "params": {"lines": [3, 3]}}]},
            {"at": "out", "do": [{"object": "src", "action": "clear"}]},
        ],
    }


def paths(errors: list[dict]) -> list[str]:
    return [e["path"] for e in errors]


# ---------------------------------------------------------------------------
# A valid scene
# ---------------------------------------------------------------------------

def test_a_valid_scene_is_parsed_in_order():
    scene, errors = parse_scene(valid_scene())
    assert errors == []
    assert scene is not None
    assert scene.version == 1 and scene.title == "Adding two numbers"
    assert [(s.id, s.say) for s in scene.steps] == [
        ("intro", "Two names hold numbers."), ("sum", "Then we add them."), ("out", "And print the result."),
    ]
    assert [(o.id, o.primitive) for o in scene.objects] == [("src", "code")]
    assert scene.objects[0].params == {"code": CODE, "language": "python"}


def test_the_state_after_each_step_folds_every_cue_so_far():
    scene, _ = parse_scene(valid_scene())
    assert scene is not None
    assert scene.state_at(0) == {"src": {"visible": True, "lines": [1, 2]}}
    assert scene.state_at(1) == {"src": {"visible": True, "lines": [3, 3]}}
    assert scene.state_at(2) == {"src": {"visible": True, "lines": None}}


def test_a_step_without_a_cue_keeps_the_previous_state():
    raw = valid_scene()
    raw["cues"] = raw["cues"][:1]
    scene, errors = parse_scene(raw)
    assert errors == [] and scene is not None
    assert scene.state_at(2) == {"src": {"visible": True, "lines": [1, 2]}}


def test_objects_can_start_hidden_and_be_shown_or_hidden_by_a_cue():
    raw = valid_scene()
    raw["objects"][0]["hidden"] = True
    raw["cues"] = [
        {"at": "sum", "do": [{"object": "src", "action": "show"}]},
        {"at": "out", "do": [{"object": "src", "action": "hide"}]},
    ]
    scene, errors = parse_scene(raw)
    assert errors == [] and scene is not None
    assert [scene.state_at(i)["src"]["visible"] for i in range(3)] == [False, True, False]


def test_actions_in_one_cue_apply_in_order():
    raw = valid_scene()
    raw["cues"] = [{"at": "intro", "do": [
        {"object": "src", "action": "focus", "params": {"lines": [1, 1]}},
        {"object": "src", "action": "focus", "params": {"lines": [4, 4]}},
    ]}]
    scene, _ = parse_scene(raw)
    assert scene is not None and scene.state_at(0)["src"]["lines"] == [4, 4]


def test_cues_and_objects_are_optional_and_say_is_trimmed():
    scene, errors = parse_scene({"version": 1, "title": "Talk", "steps": [{"id": "a", "say": "  Hi. "}]})
    assert errors == [] and scene is not None
    assert scene.steps[0].say == "Hi." and scene.objects == () and scene.state_at(0) == {}


def test_language_defaults_to_empty():
    raw = valid_scene()
    del raw["objects"][0]["params"]["language"]
    scene, errors = parse_scene(raw)
    assert errors == [] and scene is not None and scene.objects[0].params["language"] == ""


def test_the_documented_example_scene_is_valid():
    example = json.loads((DOCS / "scene.example.json").read_text(encoding="utf-8"))
    scene, errors = parse_scene(example)
    assert errors == [] and scene is not None and len(scene.steps) >= 2


def test_the_json_schema_lists_the_registered_primitives():
    schema = json.loads((DOCS / "scene.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["version"]["const"] == 1
    assert set(schema["properties"]["objects"]["items"]["properties"]["primitive"]["enum"]) == set(PRIMITIVES)


# ---------------------------------------------------------------------------
# Invalid scenes: every problem, with a path
# ---------------------------------------------------------------------------

def test_a_scene_must_be_an_object():
    scene, errors = parse_scene([1, 2])
    assert scene is None and paths(errors) == [""]


@pytest.mark.parametrize(
    "mutate, path, fragment",
    [
        (lambda s: s.update(version=2), "version", "version must be 1"),
        (lambda s: s.pop("version"), "version", "version must be 1"),
        (lambda s: s.update(title="  "), "title", "non-empty string"),
        (lambda s: s.update(steps=[]), "steps", "non-empty list"),
        (lambda s: s.update(extra=1), "extra", "unknown field"),
        (lambda s: s["steps"][1].update(say=""), "steps[1].say", "non-empty string"),
        (lambda s: s["steps"][1].update(id="intro"), "steps[1].id", "duplicate"),
        (lambda s: s["steps"][1].update(id="has space"), "steps[1].id", "letters, digits"),
        (lambda s: s["steps"][1].update(voice="x"), "steps[1].voice", "unknown field"),
        (lambda s: s["objects"][0].update(primitive="graph"), "objects[0].primitive", "unknown primitive"),
        (lambda s: s["objects"][0].update(hidden="yes"), "objects[0].hidden", "true or false"),
        (lambda s: s["objects"][0]["params"].update(code=""), "objects[0].params.code", "non-empty string"),
        (lambda s: s["objects"][0]["params"].update(language=3), "objects[0].params.language", "string"),
        (lambda s: s["objects"][0]["params"].update(theme="x"), "objects[0].params.theme", "unknown field"),
        (lambda s: s["cues"][0].update(at="nope"), "cues[0].at", "unknown step"),
        (lambda s: s["cues"][1].update(at="intro"), "cues[1].at", "already has a cue"),
        (lambda s: s["cues"][0].update(do=[]), "cues[0].do", "non-empty list"),
        (lambda s: s["cues"][0]["do"][0].update(object="ghost"), "cues[0].do[0].object", "unknown object"),
        (lambda s: s["cues"][0]["do"][0].update(action="trace"), "cues[0].do[0].action", "code objects support"),
        (lambda s: s["cues"][0]["do"][0].update(params={"lines": [3, 9]}), "cues[0].do[0].params.lines", "only has 4 lines"),
        (lambda s: s["cues"][0]["do"][0].update(params={"lines": [2, 1]}), "cues[0].do[0].params.lines", "before its start"),
        (lambda s: s["cues"][0]["do"][0].update(params={}), "cues[0].do[0].params.lines", "[start, end]"),
        (lambda s: s["cues"][2]["do"][0].update(params={"lines": [1, 1]}), "cues[2].do[0].params", "takes no params"),
        (lambda s: s["cues"][0]["do"][0]["params"].update(color="red"), "cues[0].do[0].params.color", "unknown field"),
    ],
)
def test_each_problem_is_reported_with_its_path(mutate, path, fragment):
    raw = valid_scene()
    mutate(raw)
    scene, errors = parse_scene(raw)
    assert scene is None
    assert path in paths(errors), errors
    assert fragment in next(e["message"] for e in errors if e["path"] == path)


def test_every_problem_is_reported_at_once():
    raw = valid_scene()
    raw["steps"][0]["say"] = ""
    raw["objects"][0]["primitive"] = "graph"
    raw["cues"][1]["at"] = "nope"
    _, errors = parse_scene(raw)
    assert {"steps[0].say", "objects[0].primitive", "cues[1].at"} <= set(paths(errors))


def test_input_is_not_mutated():
    raw = valid_scene()
    before = copy.deepcopy(raw)
    parse_scene(raw)
    assert raw == before


@pytest.mark.parametrize(
    "field, cap, make",
    [
        ("steps", MAX_STEPS, lambda i: {"id": f"s{i}", "say": "x"}),
        ("objects", MAX_OBJECTS, lambda i: {"id": f"o{i}", "primitive": "code", "params": {"code": "x"}}),
    ],
)
def test_steps_and_objects_are_capped(field, cap, make):
    raw = valid_scene()
    raw["cues"] = []
    raw[field] = [make(i) for i in range(cap + 1)]
    scene, errors = parse_scene(raw)
    assert scene is None and field in paths(errors)
    assert f"at most {cap}" in next(e["message"] for e in errors if e["path"] == field)


def test_actions_per_cue_are_capped():
    raw = valid_scene()
    raw["cues"][0]["do"] = [{"object": "src", "action": "clear"}] * (MAX_ACTIONS_PER_CUE + 1)
    _, errors = parse_scene(raw)
    assert "cues[0].do" in paths(errors)


# ---------------------------------------------------------------------------
# explain() as a scene
# ---------------------------------------------------------------------------

def test_a_walkthrough_becomes_a_one_code_object_scene():
    walkthrough, _ = parse_walkthrough(CODE, "python", [
        {"say": "Two names.", "focus": {"lines": [1, 2]}},
        {"say": "Overview."},
    ])
    assert walkthrough is not None
    scene = scene_from_walkthrough(walkthrough)
    assert [(o.primitive, o.params) for o in scene.objects] == [("code", {"code": CODE, "language": "python"})]
    assert [s.say for s in scene.steps] == ["Two names.", "Overview."]
    assert scene.state_at(0) == {"code": {"visible": True, "lines": [1, 2]}}
    assert scene.state_at(1) == {"code": {"visible": True, "lines": None}}


def test_state_at_rejects_indexes_outside_the_steps():
    scene, _ = parse_scene(valid_scene())
    assert scene is not None
    for index in (-1, 3):
        with pytest.raises(IndexError):
            scene.state_at(index)


def test_the_schema_rejects_blank_text_like_the_server():
    schema = json.loads((DOCS / "scene.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["title"]["pattern"] == r"\S"
    assert schema["properties"]["steps"]["items"]["properties"]["say"]["pattern"] == r"\S"
