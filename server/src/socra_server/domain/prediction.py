"""Prediction results: the real outcome of one operation on a structure that is on screen.

Pure: no I/O. The operation has the shape a scene cue uses for that structure kind
(``{"action": "insert", "params": {"key": 7}}``) and is applied with the same reducers, so the
state and its ``last`` metadata are exactly what a cue would have produced.
"""
from __future__ import annotations

import dataclasses
from typing import Any

from socra_server.domain import structures
from socra_server.domain.scene import Scene

Errors = list[str]
_FIELDS = {"object", "op"}
_OP_FIELDS = {"action", "params"}


@dataclasses.dataclass(frozen=True)
class Prediction:
    object: str
    state: dict
    outcome: str


def _shown(value: Any) -> str:
    return f"'{value}'" if isinstance(value, str) else str(value)


def _path(path: list) -> str:
    return " -> ".join(_shown(k) for k in path)


def describe(last: dict) -> str:
    """The factual outcome of an operation, in words, from its ``last`` metadata."""
    op = last["op"]
    if op == "insert" and "bucket" in last:
        base = f"Inserted {_shown(last['key'])}: hash {last['hash']} lands in bucket {last['bucket']}, position {last['position']} of its chain"
        return base + (", a collision (the bucket already held a key)." if last["collision"] else ", no collision.")
    if op == "insert":
        return f"Inserted {_shown(last['key'])} after visiting {_path(last['path'][:-1]) or 'nothing (the tree was empty)'}; the path was {_path(last['path'])}."
    if op == "lookup" and "bucket" in last:
        found = f"found at position {last['position']}" if last["found"] else "not found"
        return f"Looked up {_shown(last['key'])}: bucket {last['bucket']}, {found} after {last['probes']} probe(s)."
    if op == "lookup":
        found = "found" if last["found"] else "not found"
        return f"Looked up {_shown(last['key'])}: {found}; the path was {_path(last['path']) or 'empty'}."
    if op == "remove":
        return f"Removed {_shown(last['key'])} from bucket {last['bucket']}, position {last['position']}."
    if op == "highlight" and "key" in last:
        return f"Highlighted {_shown(last['key'])}; the path was {_path(last['path'])}."
    if op == "highlight":
        return f"Highlighted cells {', '.join(map(str, last['indexes']))}."
    if op == "set":
        return f"Set cell {last['index']} to {_shown(last['value'])} (it held {_shown(last['previous'])})."
    if op == "swap":
        return f"Swapped cells {last['indexes'][0]} and {last['indexes'][1]}."
    if op == "compare":
        i, j = last["indexes"]
        verdict = "equal" if last["result"] == "equal" else f"{last['result']} than cell {j}"
        return f"Compared cells {i} and {j}: cell {i} is {verdict}." if last["result"] != "equal" else f"Compared cells {i} and {j}: they are equal."
    if op in ("push", "enqueue"):
        return f"{'Pushed' if op == 'push' else 'Enqueued'} {_shown(last['value'])} at cell {last['index']}."
    if op in ("pop", "dequeue"):
        return f"{'Popped' if op == 'pop' else 'Dequeued'} {_shown(last['value'])} from cell {last['index']}."
    if op == "peek":
        return f"Peeked at {_shown(last['value'])} in cell {last['index']}; nothing was removed."
    return f"Applied {op}."


def predict(scene: Scene, states: dict[str, dict], raw: Any) -> tuple[Prediction | None, Errors]:
    """Apply the operation to the state on screen; the new state of that object, or ``path: message`` lines."""
    if not isinstance(raw, dict):
        return None, ["args: expected an object with object and op"]
    extra = sorted(set(raw) - _FIELDS)
    if extra:
        return None, [f"{field}: unknown field; show_result takes object and op" for field in extra]
    structs = {o.id: o for o in scene.objects if o.primitive == "structure"}
    name = raw.get("object")
    if not isinstance(name, str) or name not in structs:
        known = ", ".join(structs) or "none"
        return None, [f"object: {name!r} is not a structure of the scene on screen (structures: {known})"]
    current = states[name]
    if not current.get("visible", True):
        return None, [f"object: {name!r} is hidden on screen right now"]
    op = raw.get("op")
    if not isinstance(op, dict):
        return None, ['op: op must be an object like {"action": "insert", "params": {"key": 7}}']
    unknown = sorted(set(op) - _OP_FIELDS)
    if unknown:
        return None, [f"op.{field}: unknown field; op takes action and params" for field in unknown]
    action, kind = op.get("action"), current["kind"]
    supported = structures.OPERATIONS[kind]
    if action not in supported:
        return None, [f"op.action: {action!r} is not an operation of this {kind}; use {', '.join(supported)}"]
    args, problems = structures.parse_args(current, action, op.get("params"))
    if problems:
        return None, [f"op.params.{field}: {message}" if field else f"op.params: {message}" for field, message in problems]
    try:
        new_state = structures.reduce(current, action, args)
    except structures.StructureError as exc:
        return None, [f"op: {exc}"]
    return Prediction(name, new_state, describe(new_state["last"])), []
