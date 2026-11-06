"""Pure rules of a narrated scene — no I/O.

A scene is what Socra says (ordered steps), what it shows (objects, each drawn by a
primitive) and cues that bind visual actions to the moment a step starts speaking.
Validation reports every problem with a path such as ``cues[0].do[1].params.lines``.
The visual state after each step is resolved here, by folding every cue up to that
step, so going back, repeating or reconnecting always shows the exact same picture.

See ``server/docs/scenes.md`` for the contract and ``scene.schema.json`` for its schema.
"""
from __future__ import annotations

import copy
import dataclasses
import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from socra_server.domain import structures
from socra_server.domain.walkthrough import Walkthrough

VERSION = 1
MAX_STEPS = 60
MAX_OBJECTS = 16
MAX_ACTIONS_PER_CUE = 16

PRESENT_PURPOSE = "Use to explain something out loud while the page changes what it shows, step by step."

# How a caller writes a scene; both the MCP tool and the agent-session tool describe it so.
SCENE_GUIDE = (
    'scene is {"version": 1, "title", "objects", "steps", "cues"}: '
    'objects [{"id", "primitive", "params", "hidden"?}] are what can be shown '
    '(primitive "code": params {"code", "language"?}; primitive "headline": params {"text"}, '
    "a title or key term of at most 24 characters on one line, drawn large with the page's "
    'particles; the page shows the first visible headline; primitive "shape": params {"shape", "wireframe"?}, '
    "a 3D solid assembled by the particles, in the state palette's colours). "
    "Use shape to show a body (cube, cylinder, cone, sphere, torus); a visible shape takes the stage "
    "over a headline, so the headline is not drawn while it is visible. Use a headline only for one "
    "key concept worth highlighting, not as a caption for every step. Never draw figures as ASCII art "
    "in a code block; code blocks are for real code. "
    'primitive "diagram": params {"nodes": [{"id", "label", "group"?}], "edges": [{"from", "to", "label"?, '
    '"hidden"?}], "direction"?: "LR" (default) or "TB"}, boxes and arrows laid out by the page: you '
    "never provide coordinates. Use a diagram for call flows, request paths and system designs, with "
    "at most 25 nodes (3 to 15 read best); not for data structures. Edges are directed and join two "
    'different nodes. A diagram supports highlight {"nodes": [ids]} and dim {"nodes": [ids]} (each '
    'replaces the previous set), reveal {"from", "to"} to draw an edge declared hidden, trace '
    '{"path": [node ids]} to animate along existing edges in order (each pair must be an edge, in its '
    'direction), annotate {"node", "text"} and clear (drops highlight, dim, trace and notes). '
    'primitive "structure": params {"kind": "array"|"stack"|"queue"|"hashTable"|"tree", "items"?: the initial '
    "contents (whole numbers, or text of at most 8 characters; a tree and a mod hash table take whole numbers), "
    '"buckets"?: 2 to 8 and "hash"?: "mod" (default, whole-number keys) or "charSum" (text keys) for a hashTable}. '
    "Use a structure to teach arrays, stacks, queues, hash tables (collisions are chained) and binary search "
    "trees; not for general graphs or system flows (use a diagram). You name the operations and the page "
    "computes the result: never compute or draw bucket indexes, positions or paths yourself. Actions by kind: "
    'array set {"index", "value"}, swap {"indexes": [i, j]}, compare {"indexes": [i, j]}, highlight {"indexes": [..]}; '
    'stack push {"value"}, pop, peek; queue enqueue {"value"}, dequeue, peek; hashTable insert {"key"}, '
    'lookup {"key"}, remove {"key"}; tree insert {"key"}, lookup {"key"}, highlight {"key"}; clear drops the mark '
    "of the last operation. Operations are simulated in step order and an impossible one is rejected (pop on an "
    "empty stack, an index out of range, removing a missing key); a lookup of a missing key is allowed and shows "
    "not found. Limits: 12 items (10 in a stack or queue), 5 tree levels. "
    "Narration belongs inside the steps: after present returns, do not describe what is on screen "
    "(the last step stays up until the user speaks). "
    'steps [{"id", "say"}] are spoken in order, each on its own; '
    'cues [{"at": step id, "do": [{"object": id, "action", "params"?}]}] change the picture '
    "when that step starts. Every primitive supports show and hide; code also supports "
    'focus {"lines": [start, end]} (1-based, inclusive) and clear, which the page also '
    'marks with particles; headline supports set {"text"} to change its words; '
    'shape supports rotate {"rx"?, "ry"?, "rz"?}, reset, and set {"shape"?, "wireframe"?}. '
    "A step without a cue keeps the previous picture. Limits: 60 steps, 16 objects, one cue per step, 16 actions "
    "per cue. Blocks until the scene ends; the user may pause, repeat, go back, skip or stop "
    "meanwhile. Returns completed (steps, note), stopped (step, total), invalid (errors: each with "
    "path and message; nothing was shown, fix them and call again), busy, page_disconnected "
    "or error (message)."
)

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ID_RULE = "ids use letters, digits, '.', '_' or '-', start with a letter or digit, at most 64 characters"

State = dict[str, Any]
Errors = list[dict]


def _error(path: str, message: str) -> dict:
    return {"path": path, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unknown_fields(raw: dict, allowed: set[str], path: str) -> Errors:
    prefix = f"{path}." if path else ""
    return [_error(f"{prefix}{key}", "unknown field") for key in raw if key not in allowed]


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class ActionSpec:
    # (raw params, the object's params, path) -> normalized params and problems
    parse: Callable[[Any, dict, str], tuple[dict, Errors]]
    # (object state, normalized params) -> new object state
    apply: Callable[[State, dict], State]


@dataclasses.dataclass(frozen=True)
class Primitive:
    name: str
    # (raw params, path) -> normalized params and problems
    parse_params: Callable[[Any, str], tuple[dict, Errors]]
    initial_state: Callable[[dict], State]
    actions: Mapping[str, ActionSpec]
    # Primitives whose actions depend on the object's params (a structure's kind) narrow them here.
    actions_for: Callable[[dict], Mapping[str, ActionSpec]] | None = None


def _no_params(name: str) -> Callable[[Any, dict, str], tuple[dict, Errors]]:
    def parse(raw: Any, _object_params: dict, path: str) -> tuple[dict, Errors]:
        if raw is None or raw == {}:
            return {}, []
        return {}, [_error(path, f"{name} takes no params")]
    return parse


def _line_count(code: str) -> int:
    return len(code.removesuffix("\n").split("\n"))


def _parse_code_params(raw: Any, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "params must be an object with code and language")]
    errors = _unknown_fields(raw, {"code", "language"}, path)
    code = raw.get("code")
    if not _is_text(code):
        errors.append(_error(f"{path}.code", "code must be a non-empty string"))
    language = raw.get("language", "")
    if not isinstance(language, str):
        errors.append(_error(f"{path}.language", "language must be a string"))
    return {"code": code, "language": language}, errors


def _parse_focus(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(f"{path}.lines", "focus needs params.lines as [start, end], two whole numbers")]
    errors = _unknown_fields(raw, {"lines"}, path)
    lines = raw.get("lines")
    field = f"{path}.lines"
    if not (isinstance(lines, (list, tuple)) and len(lines) == 2 and all(_is_int(n) for n in lines)):
        return {}, errors + [_error(field, "lines must be [start, end], two whole numbers")]
    start, end = lines
    line_count = _line_count(object_params["code"])
    if start < 1:
        errors.append(_error(field, f"lines start at 1, got {start}"))
    elif end < start:
        errors.append(_error(field, f"end line {end} is before its start {start}"))
    elif end > line_count:
        errors.append(_error(field, f"lines {start}-{end} are outside the code, which only has {line_count} lines"))
    return {"lines": [start, end]}, errors


CODE = Primitive(
    name="code",
    parse_params=_parse_code_params,
    initial_state=lambda _params: {"lines": None},
    actions={
        # Highlight a 1-based inclusive line range; replaces any previous focus.
        "focus": ActionSpec(_parse_focus, lambda state, params: state | {"lines": list(params["lines"])}),
        "clear": ActionSpec(_no_params("clear"), lambda state, _params: state | {"lines": None}),
    },
)

# Every primitive supports these; they toggle the object's ``visible`` state.
_COMMON_ACTIONS: dict[str, ActionSpec] = {
    "show": ActionSpec(_no_params("show"), lambda state, _params: state | {"visible": True}),
    "hide": ActionSpec(_no_params("hide"), lambda state, _params: state | {"visible": False}),
}

MAX_HEADLINE_CHARS = 24


def _parse_headline_text(raw: Any, path: str) -> tuple[str, Errors]:
    field = f"{path}.text"
    if not _is_text(raw):
        return "", [_error(field, "text must be a non-empty string")]
    text = raw.strip()
    if "\n" in text or "\r" in text:
        return text, [_error(field, "text must fit on one line")]
    if len(text) > MAX_HEADLINE_CHARS:
        return text, [_error(field, f"text holds at most {MAX_HEADLINE_CHARS} characters, got {len(text)}")]
    return text, []


def _parse_headline_params(raw: Any, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "params must be an object with text")]
    errors = _unknown_fields(raw, {"text"}, path)
    text, problems = _parse_headline_text(raw.get("text"), path)
    return {"text": text}, errors + problems


def _parse_set_text(raw: Any, _object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "set needs params.text, the new words")]
    errors = _unknown_fields(raw, {"text"}, path)
    text, problems = _parse_headline_text(raw.get("text"), path)
    return {"text": text}, errors + problems


# A few words the page assembles out of particles, like a title on a whiteboard.
HEADLINE = Primitive(
    name="headline",
    parse_params=_parse_headline_params,
    initial_state=lambda params: {"text": params["text"]},
    actions={
        # Replace the words; the particles reassemble into the new ones.
        "set": ActionSpec(_parse_set_text, lambda state, params: state | {"text": params["text"]}),
    },
)

ALLOWED_SHAPES = ("cube", "cylinder", "cone", "sphere", "torus")
_SHAPE_NAMES = ", ".join(ALLOWED_SHAPES)


def _parse_shape_params(raw: Any, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "params must be an object with shape")]
    errors = _unknown_fields(raw, {"shape", "wireframe"}, path)
    shape = raw.get("shape")
    if shape not in ALLOWED_SHAPES:
        errors.append(_error(f"{path}.shape", f"shape must be one of {_SHAPE_NAMES}"))
    wireframe = raw.get("wireframe", False)
    if not isinstance(wireframe, bool):
        errors.append(_error(f"{path}.wireframe", "wireframe must be a boolean"))
    return {
        "shape": shape if shape in ALLOWED_SHAPES else "",
        "wireframe": bool(wireframe) if isinstance(wireframe, bool) else False,
    }, errors


def _parse_rotate(raw: Any, _object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "rotate needs params object with rx, ry, or rz")]
    errors = _unknown_fields(raw, {"rx", "ry", "rz"}, path)
    normalized: dict[str, float] = {}
    for axis in ("rx", "ry", "rz"):
        if axis in raw:
            val = raw[axis]
            if not _is_number(val):
                errors.append(_error(f"{path}.{axis}", f"{axis} must be a number"))
            elif not math.isfinite(val):
                errors.append(_error(f"{path}.{axis}", f"{axis} must be a finite number"))
            else:
                normalized[axis] = float(val)
    if not any(axis in raw for axis in ("rx", "ry", "rz")):
        errors.append(_error(path, "rotate needs at least one of rx, ry, rz"))
    return normalized, errors


def _parse_shape_set(raw: Any, _object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "set needs params object with shape or wireframe")]
    errors = _unknown_fields(raw, {"shape", "wireframe"}, path)
    normalized: dict[str, Any] = {}
    if "shape" in raw:
        shape = raw["shape"]
        if shape not in ALLOWED_SHAPES:
            errors.append(_error(f"{path}.shape", f"shape must be one of {_SHAPE_NAMES}"))
        else:
            normalized["shape"] = shape
    if "wireframe" in raw:
        wireframe = raw["wireframe"]
        if not isinstance(wireframe, bool):
            errors.append(_error(f"{path}.wireframe", "wireframe must be a boolean"))
        else:
            normalized["wireframe"] = wireframe
    if not any(key in raw for key in ("shape", "wireframe")):
        errors.append(_error(path, "set needs at least one of shape, wireframe"))
    return normalized, errors


def _apply_rotate(state: State, params: dict) -> State:
    return state | {k: params[k] for k in ("rx", "ry", "rz") if k in params}


# A 3D geometric solid assembled by the particle field in the voice stage; it follows the state palette.
SHAPE = Primitive(
    name="shape",
    parse_params=_parse_shape_params,
    initial_state=lambda params: {
        "shape": params["shape"],
        "wireframe": params["wireframe"],
        "rx": 0.0,
        "ry": 0.0,
        "rz": 0.0,
    },
    actions={
        "rotate": ActionSpec(_parse_rotate, _apply_rotate),
        "reset": ActionSpec(
            _no_params("reset"),
            lambda state, _params: state | {"rx": 0.0, "ry": 0.0, "rz": 0.0},
        ),
        "set": ActionSpec(_parse_shape_set, lambda state, params: state | params),
    },
)

MAX_DIAGRAM_NODES = 25
MAX_DIAGRAM_EDGES = 60
MAX_NODE_LABEL_CHARS = 40
MAX_NODE_GROUP_CHARS = 24
MAX_EDGE_LABEL_CHARS = 30
MAX_NOTE_CHARS = 60
MAX_TRACE_NODES = 30
DIAGRAM_DIRECTIONS = ("TB", "LR")
DEFAULT_DIAGRAM_DIRECTION = "LR"


def _one_line_text(raw: Any, field: str, name: str, limit: int) -> tuple[str, Errors]:
    if not _is_text(raw):
        return "", [_error(field, f"{name} must be a non-empty string")]
    text = raw.strip()
    if "\n" in text or "\r" in text:
        return text, [_error(field, f"{name} must fit on one line")]
    if len(text) > limit:
        return text, [_error(field, f"{name} holds at most {limit} characters, got {len(text)}")]
    return text, []


def _optional_one_line(raw: dict, key: str, field: str, limit: int) -> tuple[str, Errors]:
    value = raw.get(key, "")
    if not isinstance(value, str):
        return "", [_error(field, f"{key} must be a string")]
    if not value.strip():
        return "", []
    return _one_line_text(value, field, key, limit)


def _parse_diagram_nodes(raw: Any, path: str) -> tuple[list[dict], Errors]:
    field = f"{path}.nodes"
    if not isinstance(raw, list) or not raw:
        return [], [_error(field, "nodes must be a non-empty list")]
    if len(raw) > MAX_DIAGRAM_NODES:
        return [], [_error(field, f"nodes must have at most {MAX_DIAGRAM_NODES} items, got {len(raw)}")]
    nodes: list[dict] = []
    seen: set[str] = set()
    errors: Errors = []
    for i, item in enumerate(raw):
        item_path = f"{field}[{i}]"
        if not isinstance(item, dict):
            errors.append(_error(item_path, "a node must be an object with id, label and optional group"))
            continue
        errors += _unknown_fields(item, {"id", "label", "group"}, item_path)
        node_id, problems = _parse_id(item, item_path, seen, "node")
        errors += problems
        label, problems = _one_line_text(item.get("label"), f"{item_path}.label", "label", MAX_NODE_LABEL_CHARS)
        errors += problems
        group, problems = _optional_one_line(item, "group", f"{item_path}.group", MAX_NODE_GROUP_CHARS)
        errors += problems
        if node_id:
            nodes.append({"id": node_id, "label": label, "group": group})
    return nodes, errors


def _parse_diagram_edges(raw: Any, node_ids: set[str], path: str) -> tuple[list[dict], Errors]:
    field = f"{path}.edges"
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        return [], [_error(field, "edges must be a list")]
    if len(raw) > MAX_DIAGRAM_EDGES:
        return [], [_error(field, f"edges must have at most {MAX_DIAGRAM_EDGES} items, got {len(raw)}")]
    edges: list[dict] = []
    pairs: set[tuple[str, str]] = set()
    errors: Errors = []
    for i, item in enumerate(raw):
        item_path = f"{field}[{i}]"
        if not isinstance(item, dict):
            errors.append(_error(item_path, "an edge must be an object with from, to and optional label"))
            continue
        errors += _unknown_fields(item, {"from", "to", "label", "hidden"}, item_path)
        ends = []
        for end in ("from", "to"):
            value = item.get(end)
            if not isinstance(value, str) or value not in node_ids:
                errors.append(_error(f"{item_path}.{end}", f"unknown node {value!r}"))
            else:
                ends.append(value)
        label, problems = _optional_one_line(item, "label", f"{item_path}.label", MAX_EDGE_LABEL_CHARS)
        errors += problems
        hidden = item.get("hidden", False)
        if not isinstance(hidden, bool):
            errors.append(_error(f"{item_path}.hidden", "hidden must be true or false"))
        if len(ends) == 2:
            pair = (ends[0], ends[1])
            if pair[0] == pair[1]:
                errors.append(_error(item_path, f"an edge cannot connect a node to itself ({pair[0]!r})"))
            elif pair in pairs:
                errors.append(_error(item_path, f"duplicate edge {pair[0]} -> {pair[1]}"))
            else:
                pairs.add(pair)
                edges.append({"from": pair[0], "to": pair[1], "label": label, "hidden": hidden is True})
    return edges, errors


def _parse_diagram_params(raw: Any, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "params must be an object with nodes, edges and optional direction")]
    errors = _unknown_fields(raw, {"nodes", "edges", "direction"}, path)
    nodes, problems = _parse_diagram_nodes(raw.get("nodes"), path)
    errors += problems
    edges, problems = _parse_diagram_edges(raw.get("edges"), {n["id"] for n in nodes}, path)
    errors += problems
    direction = raw.get("direction", DEFAULT_DIAGRAM_DIRECTION)
    if direction not in DIAGRAM_DIRECTIONS:
        errors.append(_error(f"{path}.direction", f"direction must be one of {', '.join(DIAGRAM_DIRECTIONS)}"))
        direction = DEFAULT_DIAGRAM_DIRECTION
    return {"nodes": nodes, "edges": edges, "direction": direction}, errors


def _node_ids_of(params: dict) -> set[str]:
    return {node["id"] for node in params["nodes"]}


def _edge_pairs_of(params: dict) -> set[tuple[str, str]]:
    return {(edge["from"], edge["to"]) for edge in params["edges"]}


def _parse_node_list(raw: Any, name: str, node_ids: set[str], path: str, *, minimum: int = 1) -> tuple[list[str], Errors]:
    field = f"{path}.{name}"
    if not isinstance(raw, list):
        raw = []
    if len(raw) < minimum:
        message = f"{name} must be a non-empty list of node ids" if minimum == 1 else f"{name} must list at least two node ids"
        return [], [_error(field, message)]
    if len(raw) > MAX_TRACE_NODES:
        return [], [_error(field, f"{name} must have at most {MAX_TRACE_NODES} items, got {len(raw)}")]
    errors: Errors = []
    ids: list[str] = []
    for i, value in enumerate(raw):
        if not isinstance(value, str) or value not in node_ids:
            errors.append(_error(f"{field}[{i}]", f"unknown node {value!r}"))
        else:
            ids.append(value)
    return ids, errors


def _node_set_parser(action: str) -> Callable[[Any, dict, str], tuple[dict, Errors]]:
    def parse(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
        if not isinstance(raw, dict):
            return {}, [_error(path, f"{action} needs params.nodes, a list of node ids")]
        errors = _unknown_fields(raw, {"nodes"}, path)
        ids, problems = _parse_node_list(raw.get("nodes"), "nodes", _node_ids_of(object_params), path)
        return {"nodes": list(dict.fromkeys(ids))}, errors + problems
    return parse


def _parse_edge_ref(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "reveal needs params.from and params.to, the node ids of an edge")]
    errors = _unknown_fields(raw, {"from", "to"}, path)
    ids = _node_ids_of(object_params)
    ends = []
    for end in ("from", "to"):
        value = raw.get(end)
        if not isinstance(value, str) or value not in ids:
            errors.append(_error(f"{path}.{end}", f"unknown node {value!r}"))
        else:
            ends.append(value)
    if len(ends) == 2 and (ends[0], ends[1]) not in _edge_pairs_of(object_params):
        errors.append(_error(path, f"no edge {ends[0]} -> {ends[1]} in this diagram"))
    return {"from": raw.get("from"), "to": raw.get("to")}, errors


def _parse_trace(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "trace needs params.path, a list of node ids to follow along edges")]
    errors = _unknown_fields(raw, {"path"}, path)
    nodes, problems = _parse_node_list(raw.get("path"), "path", _node_ids_of(object_params), path, minimum=2)
    errors += problems
    if not problems:
        pairs = _edge_pairs_of(object_params)
        for a, b in zip(nodes, nodes[1:]):
            if (a, b) not in pairs:
                errors.append(_error(f"{path}.path", f"no edge {a} -> {b} in this diagram; a path follows edges in their direction"))
                break
    return {"path": nodes}, errors


def _parse_annotate(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "annotate needs params.node and params.text")]
    errors = _unknown_fields(raw, {"node", "text"}, path)
    node = raw.get("node")
    if not isinstance(node, str) or node not in _node_ids_of(object_params):
        errors.append(_error(f"{path}.node", f"unknown node {node!r}"))
    text, problems = _one_line_text(raw.get("text"), f"{path}.text", "text", MAX_NOTE_CHARS)
    return {"node": node, "text": text}, errors + problems


def _diagram_initial(params: dict) -> State:
    return {
        "highlighted": [],
        "dimmed": [],
        "revealed": [{"from": e["from"], "to": e["to"]} for e in params["edges"] if not e["hidden"]],
        "trace": [],
        "notes": {},
    }


def _with_edges(revealed: list[dict], pairs: list[tuple[str, str]]) -> list[dict]:
    known = {(e["from"], e["to"]) for e in revealed}
    return revealed + [{"from": a, "to": b} for a, b in dict.fromkeys(pairs) if (a, b) not in known]


def _apply_highlight(state: State, params: dict) -> State:
    return state | {
        "highlighted": list(params["nodes"]),
        "dimmed": [n for n in state["dimmed"] if n not in params["nodes"]],
    }


def _apply_dim(state: State, params: dict) -> State:
    return state | {
        "dimmed": list(params["nodes"]),
        "highlighted": [n for n in state["highlighted"] if n not in params["nodes"]],
    }


def _apply_trace(state: State, params: dict) -> State:
    path = params["path"]
    return state | {"trace": list(path), "revealed": _with_edges(state["revealed"], list(zip(path, path[1:])))}


# Boxes and arrows laid out by the page; the model never gives coordinates.
DIAGRAM = Primitive(
    name="diagram",
    parse_params=_parse_diagram_params,
    initial_state=_diagram_initial,
    actions={
        # highlight and dim each replace their previous set; a node is never both.
        "highlight": ActionSpec(_node_set_parser("highlight"), _apply_highlight),
        "dim": ActionSpec(_node_set_parser("dim"), _apply_dim),
        "reveal": ActionSpec(
            _parse_edge_ref,
            lambda state, params: state | {"revealed": _with_edges(state["revealed"], [(params["from"], params["to"])])},
        ),
        # Follows existing edges in their direction; the traced edges are revealed too.
        "trace": ActionSpec(_parse_trace, _apply_trace),
        "annotate": ActionSpec(
            _parse_annotate,
            lambda state, params: state | {"notes": state["notes"] | {params["node"]: params["text"]}},
        ),
        "clear": ActionSpec(
            _no_params("clear"),
            lambda state, _params: state | {"highlighted": [], "dimmed": [], "trace": [], "notes": {}},
        ),
    },
)

def _parse_structure_params(raw: Any, path: str) -> tuple[dict, Errors]:
    if not isinstance(raw, dict):
        return {}, [_error(path, "params must be an object with kind and optional items, buckets and hash")]
    errors = _unknown_fields(raw, {"kind", "items", "buckets", "hash"}, path)
    kind = raw.get("kind")
    if kind not in structures.KINDS:
        return {}, errors + [_error(f"{path}.kind", f"kind must be one of {', '.join(structures.KINDS)}")]
    params: dict[str, Any] = {"kind": kind}
    items = raw.get("items", [])
    if not isinstance(items, list):
        errors.append(_error(f"{path}.items", "items must be a list of the initial contents"))
        items = []
    params["items"] = items
    if kind == "hashTable":
        buckets = raw.get("buckets", structures.DEFAULT_BUCKETS)
        if not _is_int(buckets) or not structures.MIN_BUCKETS <= buckets <= structures.MAX_BUCKETS:
            errors.append(_error(
                f"{path}.buckets",
                f"buckets must be a whole number from {structures.MIN_BUCKETS} to {structures.MAX_BUCKETS}",
            ))
            buckets = structures.DEFAULT_BUCKETS
        rule = raw.get("hash", structures.DEFAULT_HASH_RULE)
        if rule not in structures.HASH_RULES:
            errors.append(_error(f"{path}.hash", f"hash must be one of {', '.join(structures.HASH_RULES)}"))
            rule = structures.DEFAULT_HASH_RULE
        params |= {"buckets": buckets, "hash": rule}
    else:
        errors += [_error(f"{path}.{key}", f"{key} only applies to a hashTable") for key in ("buckets", "hash") if key in raw]
    if kind in ("array", "stack", "queue"):
        for i, value in enumerate(items):
            problem = structures.item_problem(value)
            if problem:
                errors.append(_error(f"{path}.items[{i}]", problem))
    if errors:
        return params, errors
    try:
        initial = structures.initial_state(params)
    except structures.StructureError as exc:
        return params, [_error(f"{path}.items", str(exc))]
    # The page draws this before the first step speaks, so it never rebuilds a structure itself.
    items = [v.strip() if isinstance(v, str) else v for v in items]
    return params | {"items": items, "initial": initial}, []


def _structure_spec(op: str) -> ActionSpec:
    def parse(raw: Any, object_params: dict, path: str) -> tuple[dict, Errors]:
        args, problems = structures.parse_args(object_params, op, raw)
        return args, [_error(f"{path}.{field}" if field else path, message) for field, message in problems]
    return ActionSpec(parse, lambda state, params: structures.reduce(state, op, params))


_STRUCTURE_ACTIONS = {op: _structure_spec(op) for op in structures.ALL_OPERATIONS}


def _structure_actions_for(params: dict) -> dict[str, ActionSpec]:
    supported = (*structures.OPERATIONS[params["kind"]], "clear")
    return {op: _STRUCTURE_ACTIONS[op] for op in supported}


# Array, stack, queue, hash table and binary search tree whose states the runtime computes from
# operations (one pure reducer per kind, in structures.py); the model never places an element.
STRUCTURE = Primitive(
    name="structure",
    parse_params=_parse_structure_params,
    initial_state=lambda params: copy.deepcopy(params["initial"]),
    actions=_STRUCTURE_ACTIONS,
    actions_for=_structure_actions_for,
)

PRIMITIVES: dict[str, Primitive] = {
    CODE.name: CODE, HEADLINE.name: HEADLINE, SHAPE.name: SHAPE, DIAGRAM.name: DIAGRAM, STRUCTURE.name: STRUCTURE,
}


def _actions_of(primitive: Primitive, params: dict) -> dict[str, ActionSpec]:
    specific = primitive.actions_for(params) if primitive.actions_for else primitive.actions
    return _COMMON_ACTIONS | dict(specific)


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class SceneStep:
    id: str
    say: str


@dataclasses.dataclass(frozen=True)
class SceneObject:
    id: str
    primitive: str
    params: dict
    hidden: bool = False


@dataclasses.dataclass(frozen=True)
class SceneAction:
    object: str
    action: str
    params: dict


@dataclasses.dataclass(frozen=True)
class Cue:
    at: str
    actions: tuple[SceneAction, ...]


@dataclasses.dataclass(frozen=True)
class Scene:
    version: int
    title: str
    objects: tuple[SceneObject, ...]
    steps: tuple[SceneStep, ...]
    cues: tuple[Cue, ...]
    # The visual state after each step's cue, one entry per step.
    states: tuple[dict[str, State], ...]

    def state_at(self, index: int) -> dict[str, State]:
        """Every object's state while step ``index`` (0-based) is speaking."""
        if not 0 <= index < len(self.states):
            raise IndexError(f"step index {index} is outside the scene's {len(self.states)} steps")
        return copy.deepcopy(self.states[index])

    def objects_for_page(self) -> list[dict]:
        """What the page needs to draw each object; its state comes with every step."""
        return [
            {"id": o.id, "primitive": o.primitive, "params": copy.deepcopy(o.params), "hidden": o.hidden}
            for o in self.objects
        ]


def _resolve(
    objects: tuple[SceneObject, ...],
    steps: tuple[SceneStep, ...],
    cues: tuple[Cue, ...],
    errors: Errors | None = None,
) -> tuple[dict[str, State], ...]:
    """Fold every cue, step by step. With ``errors``, an action that cannot happen (popping an
    empty stack) is reported there with its ``cues[i].do[j]`` path and its object stops changing,
    since what follows would depend on the failed action; without it the cues must be valid."""
    by_step = {cue.at: cue for cue in cues}
    cue_index = {cue.at: i for i, cue in enumerate(cues)}
    by_id = {obj.id: obj for obj in objects}
    failed: set[str] = set()
    state = {
        obj.id: {"visible": not obj.hidden} | PRIMITIVES[obj.primitive].initial_state(obj.params)
        for obj in objects
    }
    states = []
    for step in steps:
        cue = by_step.get(step.id)
        for j, action in enumerate(cue.actions if cue else ()):
            if action.object in failed:
                continue
            obj = by_id[action.object]
            spec = _actions_of(PRIMITIVES[obj.primitive], obj.params)[action.action]
            try:
                state[action.object] = spec.apply(state[action.object], action.params)
            except structures.StructureError as exc:
                if errors is None:
                    raise
                failed.add(action.object)
                errors.append(_error(f"cues[{cue_index[step.id]}].do[{j}]", f"step {step.id!r}: {exc}"))
        states.append(copy.deepcopy(state))
    return tuple(states)


def _assemble(
    title: str, objects: tuple[SceneObject, ...], steps: tuple[SceneStep, ...], cues: tuple[Cue, ...], errors: Errors | None = None,
) -> Scene:
    return Scene(VERSION, title, objects, steps, cues, _resolve(objects, steps, cues, errors))


def _list(raw: dict, key: str, cap: int, *, required: bool) -> tuple[list, Errors]:
    value = raw.get(key, None if required else [])
    if not isinstance(value, list) or (required and not value):
        kind = "a non-empty list" if required else "a list"
        return [], [_error(key, f"{key} must be {kind}")]
    if len(value) > cap:
        return [], [_error(key, f"{key} must have at most {cap} items, got {len(value)}")]
    return value, []


def _parse_id(raw: dict, path: str, seen: set[str], kind: str) -> tuple[str | None, Errors]:
    value = raw.get("id")
    if not isinstance(value, str) or not _ID.fullmatch(value):
        return None, [_error(f"{path}.id", _ID_RULE)]
    if value in seen:
        return None, [_error(f"{path}.id", f"duplicate {kind} id {value!r}")]
    seen.add(value)
    return value, []


def _parse_steps(items: list) -> tuple[list[SceneStep], set[str], Errors]:
    steps: list[SceneStep] = []
    ids: set[str] = set()
    errors: Errors = []
    for i, raw in enumerate(items):
        path = f"steps[{i}]"
        if not isinstance(raw, dict):
            errors.append(_error(path, "a step must be an object with id and say"))
            continue
        errors += _unknown_fields(raw, {"id", "say"}, path)
        step_id, problems = _parse_id(raw, path, ids, "step")
        errors += problems
        say = raw.get("say")
        if not _is_text(say):
            errors.append(_error(f"{path}.say", "say must be a non-empty string"))
        if step_id and _is_text(say):
            steps.append(SceneStep(step_id, say.strip()))
    return steps, ids, errors


def _parse_objects(items: list) -> tuple[list[SceneObject], dict[str, SceneObject | None], Errors]:
    objects: list[SceneObject] = []
    # Every well-formed id, mapped to its object or to None when the object itself is invalid.
    known: dict[str, SceneObject | None] = {}
    seen: set[str] = set()
    errors: Errors = []
    for i, raw in enumerate(items):
        path = f"objects[{i}]"
        if not isinstance(raw, dict):
            errors.append(_error(path, "an object must have id, primitive and params"))
            continue
        errors += _unknown_fields(raw, {"id", "primitive", "params", "hidden"}, path)
        object_id, problems = _parse_id(raw, path, seen, "object")
        errors += problems
        found = len(errors)
        name = raw.get("primitive")
        primitive = PRIMITIVES.get(name) if isinstance(name, str) else None
        if primitive is None:
            names = ", ".join(sorted(PRIMITIVES))
            errors.append(_error(f"{path}.primitive", f"unknown primitive {raw.get('primitive')!r}; available: {names}"))
        else:
            params, problems = primitive.parse_params(raw.get("params"), f"{path}.params")
            errors += problems
        hidden = raw.get("hidden", False)
        if not isinstance(hidden, bool):
            errors.append(_error(f"{path}.hidden", "hidden must be true or false"))
        if object_id is None:
            continue
        if primitive is None or len(errors) > found:
            known[object_id] = None
            continue
        obj = SceneObject(object_id, primitive.name, params, hidden)
        objects.append(obj)
        known[object_id] = obj
    return objects, known, errors


def _parse_action(raw: Any, path: str, objects: dict[str, SceneObject | None]) -> tuple[SceneAction | None, Errors]:
    if not isinstance(raw, dict):
        return None, [_error(path, "an action must be an object with object, action and optional params")]
    errors = _unknown_fields(raw, {"object", "action", "params"}, path)
    object_id = raw.get("object")
    if not isinstance(object_id, str) or object_id not in objects:
        return None, errors + [_error(f"{path}.object", f"unknown object {object_id!r}")]
    obj = objects[object_id]
    if obj is None:  # the object already reported its own problems
        return None, errors
    actions = _actions_of(PRIMITIVES[obj.primitive], obj.params)
    name = raw.get("action")
    spec = actions.get(name) if isinstance(name, str) else None
    if spec is None:
        supported = ", ".join(actions)
        return None, errors + [_error(f"{path}.action", f"{obj.primitive} objects support {supported}; got {name!r}")]
    params, problems = spec.parse(raw.get("params"), obj.params, f"{path}.params")
    errors += problems
    return (None if errors else SceneAction(object_id, name, params)), errors


def _parse_cues(items: list, step_ids: set[str], objects: dict[str, SceneObject | None]) -> tuple[list[Cue], Errors]:
    cues: list[Cue] = []
    cued: set[str] = set()
    errors: Errors = []
    for i, raw in enumerate(items):
        path = f"cues[{i}]"
        if not isinstance(raw, dict):
            errors.append(_error(path, "a cue must be an object with at and do"))
            continue
        errors += _unknown_fields(raw, {"at", "do"}, path)
        at = raw.get("at")
        if not isinstance(at, str) or at not in step_ids:
            errors.append(_error(f"{path}.at", f"unknown step id {at!r}"))
        elif at in cued:
            errors.append(_error(f"{path}.at", f"step {at!r} already has a cue; put every action in one cue"))
        else:
            cued.add(at)
        do = raw.get("do")
        if not isinstance(do, list) or not do:
            errors.append(_error(f"{path}.do", "do must be a non-empty list of actions"))
            continue
        if len(do) > MAX_ACTIONS_PER_CUE:
            errors.append(_error(f"{path}.do", f"a cue may have at most {MAX_ACTIONS_PER_CUE} actions, got {len(do)}"))
            continue
        actions = []
        for j, raw_action in enumerate(do):
            action, problems = _parse_action(raw_action, f"{path}.do[{j}]", objects)
            errors += problems
            if action:
                actions.append(action)
        if isinstance(at, str):
            cues.append(Cue(at, tuple(actions)))
    return cues, errors


def parse_scene(raw: Any) -> tuple[Scene | None, Errors]:
    """Validate client input. Returns the scene, or every problem found."""
    if not isinstance(raw, dict):
        return None, [_error("", "a scene must be an object with version, title, objects, steps and cues")]
    errors = _unknown_fields(raw, {"version", "title", "objects", "steps", "cues"}, "")
    version = raw.get("version")
    if not _is_int(version) or version != VERSION:
        errors.append(_error("version", f"version must be {VERSION}"))
    title = raw.get("title")
    if not _is_text(title):
        errors.append(_error("title", "title must be a non-empty string"))

    step_items, problems = _list(raw, "steps", MAX_STEPS, required=True)
    errors += problems
    object_items, problems = _list(raw, "objects", MAX_OBJECTS, required=False)
    errors += problems
    cue_items, problems = _list(raw, "cues", MAX_STEPS, required=False)
    errors += problems

    steps, step_ids, problems = _parse_steps(step_items)
    errors += problems
    objects, known, problems = _parse_objects(object_items)
    errors += problems
    cues, problems = _parse_cues(cue_items, step_ids, known)
    errors += problems

    if errors:
        return None, errors
    # Every cue is simulated in step order: an impossible operation is reported before anything is spoken.
    problems: Errors = []
    scene = _assemble(title.strip(), tuple(objects), tuple(steps), tuple(cues), problems)
    return (None, problems) if problems else (scene, [])


def scene_from_walkthrough(walkthrough: Walkthrough) -> Scene:
    """explain() input as a scene: one code object, each step focusing its lines or nothing."""
    code = SceneObject("code", CODE.name, {"code": walkthrough.code, "language": walkthrough.language})
    steps = tuple(SceneStep(f"s{n}", step.say) for n, step in enumerate(walkthrough.steps, start=1))
    cues = tuple(
        Cue(scene_step.id, (
            SceneAction("code", "focus", {"lines": list(step.lines)}) if step.lines else SceneAction("code", "clear", {}),
        ))
        for scene_step, step in zip(steps, walkthrough.steps)
    )
    # Built directly: the walkthrough is already valid, and explain() has no step cap.
    return _assemble("", (code,), steps, cues)
