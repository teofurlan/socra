"""Pointing at objects of the finished scene: the agent's targets, checked against what is on screen.

Pure: no I/O. The scene is the one still on the page and ``index`` the step whose state it shows.
"""
from __future__ import annotations

from typing import Any

from socra_server.domain.scene import Scene, SceneObject, _line_count, _node_ids_of

MAX_TARGETS = 6
# The primitives the page can visibly emphasize; a shape or headline has nothing to highlight.
POINTABLE = ("code", "diagram", "structure")
_TARGET_FIELDS = {"object", "part", "lines"}
Targets = list[dict]
Errors = list[str]


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _index(text: str) -> int | None:
    return int(text) if text.isascii() and text.isdigit() else None


def _structure_part_problem(part: str, state: dict) -> str | None:
    kind = state.get("kind")
    prefix, _, rest = part.partition(":")
    if kind in ("array", "stack", "queue") and prefix == "cell":
        count = len(state["items"])
        i = _index(rest)
        if i is None or i >= count:
            return f"{part!r} is not a cell: this {kind} has {count} cells, numbered from 0 (cell:0 to cell:{count - 1})" if count else f"{part!r} is not a cell: this {kind} is empty"
        return None
    if kind == "hashTable" and prefix == "bucket":
        count = len(state["buckets"])
        i = _index(rest)
        if i is None or i >= count:
            return f"{part!r} is not a bucket: buckets go from bucket:0 to bucket:{count - 1}"
        return None
    if kind == "hashTable" and prefix == "entry":
        bucket, _, position = rest.partition(":")
        b, p = _index(bucket), _index(position)
        if b is None or p is None or b >= len(state["buckets"]) or p >= len(state["buckets"][b]):
            return f"{part!r} is not an entry of the hash table (entry:<bucket>:<position> of a key that is there)"
        return None
    if kind == "tree" and prefix == "node":
        if rest not in {str(n["key"]) for n in state["nodes"]}:
            return f"{part!r} is not a node: the tree holds {', '.join(str(n['key']) for n in state['nodes']) or 'no keys'}"
        return None
    expected = {
        "hashTable": "bucket:<b> or entry:<b>:<pos>", "tree": "node:<key>",
    }.get(kind, "cell:<index>")
    return f"{part!r} is not a part of this {kind}; use {expected}"


def _check_target(raw: Any, objects: dict[str, SceneObject], state: dict[str, dict], path: str) -> tuple[dict | None, Errors]:
    if not isinstance(raw, dict):
        return None, [f"{path}: a target must be an object with object and optional part or lines"]
    extra = sorted(set(raw) - _TARGET_FIELDS)
    if extra:
        return None, [f"{path}: unknown field {', '.join(extra)}; targets take object, part and lines"]
    name = raw.get("object")
    obj = objects.get(name) if isinstance(name, str) else None
    if obj is None:
        known = ", ".join(objects) or "none"
        return None, [f"{path}.object: {name!r} is not an object of the scene on screen (objects: {known})"]
    if not state[name].get("visible", True):
        return None, [f"{path}.object: {name!r} is hidden on screen right now"]
    if obj.primitive not in POINTABLE:
        return None, [f"{path}.object: {name!r} is a {obj.primitive}, which cannot be highlighted; point at a code, diagram or structure object"]
    target: dict = {"object": name}
    part, lines = raw.get("part"), raw.get("lines")
    if part is not None:
        if not isinstance(part, str) or not part:
            return None, [f"{path}.part: part must be a non-empty string"]
        if obj.primitive == "diagram":
            if part not in _node_ids_of(obj.params):
                return None, [f"{path}.part: {part!r} is not a node of {name!r} (nodes: {', '.join(sorted(_node_ids_of(obj.params)))})"]
        elif obj.primitive == "structure":
            problem = _structure_part_problem(part, state[name])
            if problem:
                return None, [f"{path}.part: {problem}"]
        else:
            return None, [f"{path}.part: a {obj.primitive} has no parts; point at {name!r} alone" + (" or use lines" if obj.primitive == "code" else "")]
        target["part"] = part
    if lines is not None:
        if obj.primitive != "code":
            return None, [f"{path}.lines: lines only apply to code, and {name!r} is a {obj.primitive}"]
        if not (isinstance(lines, (list, tuple)) and len(lines) == 2 and all(_is_int(n) for n in lines)):
            return None, [f"{path}.lines: lines must be [start, end], two whole numbers"]
        start, end = lines
        count = _line_count(obj.params["code"])
        if start < 1 or end < start or end > count:
            return None, [f"{path}.lines: lines {start}-{end} are not a range inside the code, which has {count} lines (from 1)"]
        target["lines"] = [start, end]
    return target, []


def validate_targets(scene: Scene, index: int, raw: Any) -> tuple[Targets, Errors]:
    """The normalized targets, or every problem as a ``path: message`` line (never both)."""
    if not isinstance(raw, list):
        return [], ["targets: targets must be a list (empty to remove the highlight)"]
    if len(raw) > MAX_TARGETS:
        return [], [f"targets: at most {MAX_TARGETS} targets, got {len(raw)}"]
    objects = {o.id: o for o in scene.objects}
    state = scene.state_at(index)
    targets: Targets = []
    errors: Errors = []
    for i, item in enumerate(raw):
        target, problems = _check_target(item, objects, state, f"targets[{i}]")
        errors += problems
        if target is not None:
            targets.append(target)
    return ([], errors) if errors else (targets, [])
