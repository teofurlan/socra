"""The diagram primitive: params, validation, actions and per-step state."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from socra_server.domain.scene import MAX_DIAGRAM_NODES, SCENE_GUIDE, parse_scene

DOCS = Path(__file__).resolve().parents[1] / "docs"


def paths(errors: list[dict]) -> list[str]:
    return [e["path"] for e in errors]


def diagram_scene() -> dict:
    return {
        "version": 1,
        "title": "A request through the stack",
        "objects": [{
            "id": "flow",
            "primitive": "diagram",
            "params": {
                "nodes": [
                    {"id": "browser", "label": "Browser", "group": "client"},
                    {"id": "api", "label": "API", "group": "server"},
                    {"id": "db", "label": "Database", "group": "server"},
                    {"id": "cache", "label": "Cache"},
                ],
                "edges": [
                    {"from": "browser", "to": "api", "label": "GET /items"},
                    {"from": "api", "to": "db"},
                    {"from": "api", "to": "cache", "hidden": True},
                    {"from": "db", "to": "api", "label": "rows"},
                ],
            },
        }],
        "steps": [
            {"id": "intro", "say": "A browser calls the API."},
            {"id": "hit", "say": "The API reads the database."},
            {"id": "cache", "say": "Then it fills the cache."},
            {"id": "back", "say": "And the answer returns."},
            {"id": "done", "say": "That is the whole path."},
        ],
        "cues": [
            {"at": "intro", "do": [{"object": "flow", "action": "highlight", "params": {"nodes": ["browser"]}}]},
            {"at": "hit", "do": [
                {"object": "flow", "action": "highlight", "params": {"nodes": ["api", "db"]}},
                {"object": "flow", "action": "dim", "params": {"nodes": ["browser"]}},
                {"object": "flow", "action": "annotate", "params": {"node": "db", "text": "slow query"}},
            ]},
            {"at": "cache", "do": [{"object": "flow", "action": "reveal", "params": {"from": "api", "to": "cache"}}]},
            {"at": "back", "do": [{"object": "flow", "action": "trace", "params": {"path": ["browser", "api", "db", "api"]}}]},
            {"at": "done", "do": [{"object": "flow", "action": "clear"}]},
        ],
    }


EDGE_BROWSER_API = {"from": "browser", "to": "api"}
EDGE_API_DB = {"from": "api", "to": "db"}
EDGE_DB_API = {"from": "db", "to": "api"}
EDGE_API_CACHE = {"from": "api", "to": "cache"}


def flow_state(scene, step):
    return scene.state_at(step)["flow"]


def test_a_valid_diagram_scene_has_per_step_state():
    scene, errors = parse_scene(diagram_scene())
    assert errors == []
    assert flow_state(scene, 0) == {
        "visible": True,
        "highlighted": ["browser"],
        "dimmed": [],
        "revealed": [EDGE_BROWSER_API, EDGE_API_DB, EDGE_DB_API],
        "trace": [],
        "notes": {},
    }
    second = flow_state(scene, 1)
    assert second["highlighted"] == ["api", "db"]
    assert second["dimmed"] == ["browser"]
    assert second["notes"] == {"db": "slow query"}
    assert EDGE_API_CACHE not in second["revealed"]
    assert EDGE_API_CACHE in flow_state(scene, 2)["revealed"]


def test_trace_sets_the_path_and_reveals_its_edges():
    raw = diagram_scene()
    raw["cues"][2]["do"] = [{"object": "flow", "action": "trace", "params": {"path": ["browser", "api", "cache"]}}]
    scene, errors = parse_scene(raw)
    assert errors == []
    traced = flow_state(scene, 2)
    assert traced["trace"] == ["browser", "api", "cache"]
    assert EDGE_API_CACHE in traced["revealed"]


def test_clear_drops_highlight_dim_trace_and_notes_but_keeps_revealed_edges():
    scene, errors = parse_scene(diagram_scene())
    assert errors == []
    last = flow_state(scene, 4)
    assert (last["highlighted"], last["dimmed"], last["trace"], last["notes"]) == ([], [], [], {})
    assert EDGE_API_CACHE in last["revealed"]


def test_a_second_highlight_replaces_the_first_and_a_second_note_on_a_node_replaces_its_text():
    raw = diagram_scene()
    raw["cues"][1]["do"].append({"object": "flow", "action": "annotate", "params": {"node": "db", "text": "now fast"}})
    scene, errors = parse_scene(raw)
    assert errors == []
    assert flow_state(scene, 1)["highlighted"] == ["api", "db"]
    assert flow_state(scene, 1)["notes"] == {"db": "now fast"}


def test_going_back_restores_the_earlier_diagram_state():
    scene, errors = parse_scene(diagram_scene())
    assert errors == []
    first = flow_state(scene, 1)
    later = [flow_state(scene, n) for n in (2, 3, 4)]
    assert all(state != first for state in later)
    assert flow_state(scene, 1) == first
    first["notes"]["db"] = "mutated"
    assert flow_state(scene, 1)["notes"] == {"db": "slow query"}


def test_show_and_hide_toggle_the_diagram():
    raw = diagram_scene()
    raw["objects"][0]["hidden"] = True
    raw["cues"][1]["do"].append({"object": "flow", "action": "show"})
    scene, errors = parse_scene(raw)
    assert errors == []
    assert flow_state(scene, 0)["visible"] is False
    assert flow_state(scene, 1)["visible"] is True


def test_the_diagram_defaults_to_left_to_right_and_keeps_a_chosen_direction():
    raw = diagram_scene()
    scene, errors = parse_scene(raw)
    assert errors == []
    assert scene.objects_for_page()[0]["params"]["direction"] == "LR"
    raw["objects"][0]["params"]["direction"] = "TB"
    scene, errors = parse_scene(raw)
    assert errors == []
    assert scene.objects_for_page()[0]["params"]["direction"] == "TB"


def test_the_page_receives_normalized_diagram_params():
    scene, _ = parse_scene(diagram_scene())
    params = scene.objects_for_page()[0]["params"]
    assert params["nodes"][3] == {"id": "cache", "label": "Cache", "group": ""}
    assert params["edges"][0] == {"from": "browser", "to": "api", "label": "GET /items", "hidden": False}
    assert params["edges"][2] == {"from": "api", "to": "cache", "label": "", "hidden": True}


def many_nodes(count: int) -> list[dict]:
    return [{"id": f"n{i}", "label": f"Node {i}"} for i in range(count)]


def test_the_node_cap_is_25():
    assert MAX_DIAGRAM_NODES == 25


def test_a_diagram_may_have_the_most_nodes_and_one_over_is_rejected():
    raw = diagram_scene()
    raw["objects"][0]["params"] = {"nodes": many_nodes(MAX_DIAGRAM_NODES), "edges": []}
    raw["cues"] = []
    scene, errors = parse_scene(raw)
    assert errors == [] and scene is not None
    raw["objects"][0]["params"] = {"nodes": many_nodes(MAX_DIAGRAM_NODES + 1), "edges": []}
    scene, errors = parse_scene(raw)
    assert scene is None
    assert f"at most {MAX_DIAGRAM_NODES}" in next(e["message"] for e in errors if e["path"] == "objects[0].params.nodes")


def with_params(mutate):
    raw = diagram_scene()
    mutate(raw["objects"][0]["params"])
    return raw


@pytest.mark.parametrize(
    ("mutate", "path", "fragment"),
    [
        (lambda p: p.pop("nodes"), "objects[0].params.nodes", "nodes must be a non-empty list"),
        (lambda p: p.update(nodes=[]), "objects[0].params.nodes", "nodes must be a non-empty list"),
        (lambda p: p.update(nodes="a"), "objects[0].params.nodes", "nodes must be a non-empty list"),
        (lambda p: p.update(extra=1), "objects[0].params.extra", "unknown field"),
        (lambda p: p.update(direction="diagonal"), "objects[0].params.direction", "direction must be one of TB, LR"),
        (lambda p: p["nodes"][0].update(id="a b"), "objects[0].params.nodes[0].id", "ids use letters"),
        (lambda p: p["nodes"][1].update(id="browser"), "objects[0].params.nodes[1].id", "duplicate node id 'browser'"),
        (lambda p: p["nodes"][0].pop("label"), "objects[0].params.nodes[0].label", "label must be a non-empty string"),
        (lambda p: p["nodes"][0].update(label="x" * 41), "objects[0].params.nodes[0].label", "at most 40 characters"),
        (lambda p: p["nodes"][0].update(label="two\nlines"), "objects[0].params.nodes[0].label", "one line"),
        (lambda p: p["nodes"][0].update(group="g" * 25), "objects[0].params.nodes[0].group", "at most 24 characters"),
        (lambda p: p["nodes"][0].update(group=3), "objects[0].params.nodes[0].group", "group must be a string"),
        (lambda p: p["nodes"][0].update(color="red"), "objects[0].params.nodes[0].color", "unknown field"),
        (lambda p: p["nodes"].__setitem__(0, "browser"), "objects[0].params.nodes[0]", "a node must be an object"),
        (lambda p: p["edges"][0].update(to="nowhere"), "objects[0].params.edges[0].to", "unknown node 'nowhere'"),
        (lambda p: p["edges"][1].update({"from": "ghost"}), "objects[0].params.edges[1].from", "unknown node 'ghost'"),
        (lambda p: p["edges"][0].pop("to"), "objects[0].params.edges[0].to", "unknown node None"),
        (lambda p: p["edges"][0].update(to="browser"), "objects[0].params.edges[0]", "connect a node to itself"),
        (lambda p: p["edges"].append({"from": "browser", "to": "api"}), "objects[0].params.edges[4]", "duplicate edge browser -> api"),
        (lambda p: p["edges"][0].update(label="x" * 31), "objects[0].params.edges[0].label", "at most 30 characters"),
        (lambda p: p["edges"][0].update(label=4), "objects[0].params.edges[0].label", "label must be a string"),
        (lambda p: p["edges"][0].update(hidden="yes"), "objects[0].params.edges[0].hidden", "hidden must be true or false"),
        (lambda p: p["edges"].extend({"from": "api", "to": "db"} for _ in range(60)), "objects[0].params.edges", "at most 60"),
    ],
)
def test_each_diagram_problem_is_reported_with_its_path(mutate, path, fragment):
    scene, errors = parse_scene(with_params(mutate))
    assert scene is None
    assert path in paths(errors), errors
    assert fragment in next(e["message"] for e in errors if e["path"] == path)


def cue_with(action: str, params):
    raw = diagram_scene()
    do = {"object": "flow", "action": action}
    if params is not None:
        do["params"] = params
    raw["cues"][0]["do"] = [do]
    return raw


@pytest.mark.parametrize(
    ("action", "params", "path", "fragment"),
    [
        ("highlight", {"nodes": ["nope"]}, "cues[0].do[0].params.nodes[0]", "unknown node 'nope'"),
        ("highlight", {"nodes": []}, "cues[0].do[0].params.nodes", "non-empty list of node ids"),
        ("highlight", {}, "cues[0].do[0].params.nodes", "non-empty list of node ids"),
        ("highlight", None, "cues[0].do[0].params", "highlight needs params.nodes"),
        ("highlight", {"nodes": ["api"], "x": 1}, "cues[0].do[0].params.x", "unknown field"),
        ("dim", {"nodes": ["nope"]}, "cues[0].do[0].params.nodes[0]", "unknown node 'nope'"),
        ("dim", {"nodes": "api"}, "cues[0].do[0].params.nodes", "non-empty list of node ids"),
        ("reveal", {"from": "browser", "to": "db"}, "cues[0].do[0].params", "no edge browser -> db"),
        ("reveal", {"from": "ghost", "to": "db"}, "cues[0].do[0].params.from", "unknown node 'ghost'"),
        ("reveal", None, "cues[0].do[0].params", "reveal needs params.from and params.to"),
        ("trace", {"path": ["browser"]}, "cues[0].do[0].params.path", "at least two node ids"),
        ("trace", {"path": ["browser", "nope"]}, "cues[0].do[0].params.path[1]", "unknown node 'nope'"),
        ("trace", {"path": ["browser", "db"]}, "cues[0].do[0].params.path", "no edge browser -> db"),
        ("trace", {"path": ["api", "browser"]}, "cues[0].do[0].params.path", "no edge api -> browser"),
        ("trace", None, "cues[0].do[0].params", "trace needs params.path"),
        ("annotate", {"node": "nope", "text": "hi"}, "cues[0].do[0].params.node", "unknown node 'nope'"),
        ("annotate", {"node": "api", "text": ""}, "cues[0].do[0].params.text", "text must be a non-empty string"),
        ("annotate", {"node": "api", "text": "y" * 61}, "cues[0].do[0].params.text", "at most 60 characters"),
        ("annotate", {"node": "api", "text": "a\nb"}, "cues[0].do[0].params.text", "one line"),
        ("annotate", None, "cues[0].do[0].params", "annotate needs params.node and params.text"),
        ("clear", {"x": 1}, "cues[0].do[0].params", "clear takes no params"),
    ],
)
def test_each_diagram_action_problem_is_reported_with_its_path(action, params, path, fragment):
    scene, errors = parse_scene(cue_with(action, params))
    assert scene is None
    assert path in paths(errors), errors
    assert fragment in next(e["message"] for e in errors if e["path"] == path)


def test_a_path_follows_edge_direction_and_may_cross_a_hidden_edge():
    scene, errors = parse_scene(cue_with("trace", {"path": ["api", "cache"]}))
    assert errors == []
    assert flow_state(scene, 0)["trace"] == ["api", "cache"]


def test_an_unknown_action_lists_what_a_diagram_supports():
    scene, errors = parse_scene(cue_with("rotate", {"rx": 1}))
    assert scene is None
    message = next(e["message"] for e in errors if e["path"] == "cues[0].do[0].action")
    for name in ("show", "hide", "highlight", "dim", "reveal", "trace", "annotate", "clear"):
        assert name in message


def test_a_diagram_with_a_bad_node_reference_never_reaches_the_cues():
    raw = with_params(lambda p: p["edges"][0].update(to="nowhere"))
    scene, errors = parse_scene(raw)
    assert scene is None
    assert "objects[0].params.edges[0].to" in paths(errors)


def test_the_diagram_example_scene_is_valid():
    content = json.loads((DOCS / "scene.diagram.example.json").read_text(encoding="utf-8"))
    scene, errors = parse_scene(content)
    assert errors == []
    assert scene is not None
    states = [scene.state_at(n)[o.id] for n in range(len(scene.steps)) for o in scene.objects]
    assert any(state["trace"] for state in states)


def test_the_json_schema_describes_the_diagram():
    schema = json.loads((DOCS / "scene.schema.json").read_text(encoding="utf-8"))
    assert "diagram" in schema["properties"]["objects"]["items"]["properties"]["primitive"]["enum"]
    params = schema["$defs"]["diagramParams"]
    assert params["required"] == ["nodes"]
    assert params["properties"]["nodes"]["maxItems"] == 25
    assert params["properties"]["direction"]["enum"] == ["TB", "LR"]
    actions = schema["$defs"]["action"]["properties"]["action"]["enum"]
    for name in ("highlight", "dim", "reveal", "trace", "annotate"):
        assert name in actions


def test_the_scene_guide_tells_when_to_use_a_diagram():
    guide = SCENE_GUIDE.lower()
    assert 'primitive "diagram"' in guide
    assert "call flow" in guide and "request path" in guide and "system design" in guide
    assert "never provide coordinates" in guide
    assert "at most 25 nodes" in guide
    assert "data structure" in guide
    for action in ("highlight", "dim", "reveal", "trace", "annotate"):
        assert action in guide
