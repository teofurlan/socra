"""Data structures for narrated scenes: one pure, deterministic reducer per kind — no I/O.

A structure object holds a *state* (its contents, plus ``last``: what the latest operation did,
with the results the runtime computed, such as a bucket index or a node's path). An operation
is applied with ``reduce(state, op, args)``, which returns a new state and never mutates its
input; an operation that cannot happen (popping an empty stack) raises ``StructureError``. The
scene validates a scene by folding every cue through these reducers before anything is spoken.

Kinds: ``array``, ``stack``, ``queue``, ``hashTable`` (chaining) and ``tree`` (binary search tree).
See ``server/docs/scenes.md`` for the contract.
"""
from __future__ import annotations

import copy
from collections.abc import Callable
from typing import Any

KINDS = ("array", "stack", "queue", "hashTable", "tree")
HASH_RULES = ("mod", "charSum")
DEFAULT_HASH_RULE = "mod"
DEFAULT_BUCKETS = 5
MIN_BUCKETS = 2
MAX_BUCKETS = 8
# The most elements (array cells, stack or queue entries, hash keys, tree nodes) a structure holds.
MAX_ITEMS = {"array": 12, "stack": 10, "queue": 10, "hashTable": 12, "tree": 12}
MAX_TREE_DEPTH = 5  # levels, counting the root as the first
MAX_TEXT_CHARS = 8
MAX_NUMBER = 9999

OPERATIONS: dict[str, tuple[str, ...]] = {
    "array": ("set", "swap", "compare", "highlight"),
    "stack": ("push", "pop", "peek"),
    "queue": ("enqueue", "dequeue", "peek"),
    "hashTable": ("insert", "lookup", "remove"),
    "tree": ("insert", "lookup", "highlight"),
}
ALL_OPERATIONS = tuple(dict.fromkeys(op for ops in OPERATIONS.values() for op in ops)) + ("clear",)

State = dict[str, Any]
Args = dict[str, Any]
Problems = list[tuple[str, str]]


class StructureError(ValueError):
    """An operation that cannot happen on the structure as it is now."""


_NAMES = {"array": "an array", "stack": "a stack", "queue": "a queue", "hashTable": "a hash table", "tree": "a tree"}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


# ---------------------------------------------------------------------------
# Values
# ---------------------------------------------------------------------------

def item_problem(value: Any) -> str | None:
    """Why ``value`` cannot be an element, or ``None``: a whole number or one short line of text."""
    if _is_int(value):
        if abs(value) > MAX_NUMBER:
            return f"numbers are between -{MAX_NUMBER} and {MAX_NUMBER}, got {value}"
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "text must not be blank"
        if "\n" in text or "\r" in text:
            return "text must fit on one line"
        if len(text) > MAX_TEXT_CHARS:
            return f"text holds at most {MAX_TEXT_CHARS} characters, got {len(text)}"
        return None
    return "a value must be a whole number or text"


def _clean(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _show(value: Any) -> str:
    return repr(value) if isinstance(value, str) else str(value)


def _key_problem(params_or_state: dict, key: Any) -> str | None:
    """Why ``key`` does not suit this structure, or ``None``."""
    kind = params_or_state["kind"]
    if kind == "tree":
        return None if _is_int(key) and abs(key) <= MAX_NUMBER else (
            f"tree keys must be whole numbers between -{MAX_NUMBER} and {MAX_NUMBER}"
        )
    rule = params_or_state.get("hash", DEFAULT_HASH_RULE)
    if rule == "mod":
        if not _is_int(key):
            return "the mod rule needs whole-number keys"
        return item_problem(key)
    if not isinstance(key, str):
        return "the charSum rule needs text keys"
    return item_problem(key)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def initial_state(params: dict) -> State:
    """The state a structure starts in, from its normalized params (kind, items, buckets, hash)."""
    kind = params["kind"]
    items = [_clean(v) for v in params.get("items", [])]
    cap = MAX_ITEMS[kind]
    if len(items) > cap:
        raise StructureError(f"{_NAMES[kind]} holds at most {cap} items, got {len(items)}")
    if kind == "array":
        if not items:
            raise StructureError("an array needs at least one item")
        for value in items:
            problem = item_problem(value)
            if problem:
                raise StructureError(problem)
        return {"kind": kind, "items": items, "last": None}
    if kind in ("stack", "queue"):
        for value in items:
            problem = item_problem(value)
            if problem:
                raise StructureError(problem)
        return {"kind": kind, "items": items, "last": None}
    if kind == "hashTable":
        state: State = {
            "kind": kind,
            "hash": params.get("hash", DEFAULT_HASH_RULE),
            "buckets": [[] for _ in range(params.get("buckets", DEFAULT_BUCKETS))],
            "last": None,
        }
    else:
        state = {"kind": kind, "nodes": [], "last": None}
    for key in items:
        state = _REDUCERS[kind](state, "insert", {"key": key})
    return state | {"last": None}


# ---------------------------------------------------------------------------
# Reducers
# ---------------------------------------------------------------------------

def _index_problem(index: int, count: int, name: str) -> str | None:
    if 0 <= index < count:
        return None
    return f"index {index} is outside the {name}, which has {count} item{'s' if count != 1 else ''} (valid 0-{count - 1})"


def _check_indexes(indexes: list[int], count: int) -> None:
    for index in indexes:
        problem = _index_problem(index, count, "array")
        if problem:
            raise StructureError(problem)


def _order(a: Any, b: Any) -> str:
    if _is_int(a) != _is_int(b):
        raise StructureError(f"cannot compare {_show(a)} with {_show(b)}: a number and text")
    return "less" if a < b else "greater" if a > b else "equal"


def _reduce_array(state: State, op: str, args: Args) -> State:
    items = list(state["items"])
    if op == "set":
        _check_indexes([args["index"]], len(items))
        previous = items[args["index"]]
        items[args["index"]] = args["value"]
        return state | {"items": items, "last": {"op": "set", "index": args["index"], "value": args["value"], "previous": previous}}
    indexes = list(args["indexes"])
    _check_indexes(indexes, len(items))
    if op == "swap":
        i, j = indexes
        if i == j:
            raise StructureError("swap needs two different indexes")
        items[i], items[j] = items[j], items[i]
        return state | {"items": items, "last": {"op": "swap", "indexes": indexes}}
    if op == "compare":
        return state | {"last": {"op": "compare", "indexes": indexes, "result": _order(items[indexes[0]], items[indexes[1]])}}
    return state | {"last": {"op": "highlight", "indexes": indexes}}  # highlight


def _reduce_stack(state: State, op: str, args: Args) -> State:
    items = list(state["items"])
    if op == "push":
        if len(items) >= MAX_ITEMS["stack"]:
            raise StructureError(f"the stack is full ({MAX_ITEMS['stack']} items)")
        items.append(args["value"])
        return state | {"items": items, "last": {"op": "push", "index": len(items) - 1, "value": args["value"]}}
    if not items:
        raise StructureError(f"cannot {op} an empty stack")
    top = len(items) - 1
    if op == "peek":
        return state | {"last": {"op": "peek", "index": top, "value": items[top]}}
    value = items.pop()
    return state | {"items": items, "last": {"op": "pop", "index": top, "value": value}}


def _reduce_queue(state: State, op: str, args: Args) -> State:
    items = list(state["items"])
    if op == "enqueue":
        if len(items) >= MAX_ITEMS["queue"]:
            raise StructureError(f"the queue is full ({MAX_ITEMS['queue']} items)")
        items.append(args["value"])
        return state | {"items": items, "last": {"op": "enqueue", "index": len(items) - 1, "value": args["value"]}}
    if not items:
        raise StructureError("cannot dequeue from an empty queue" if op == "dequeue" else "cannot peek an empty queue")
    if op == "peek":
        return state | {"last": {"op": "peek", "index": 0, "value": items[0]}}
    value = items.pop(0)
    return state | {"items": items, "last": {"op": "dequeue", "index": 0, "value": value}}


def hash_value(rule: str, key: Any) -> int:
    """The number a rule makes of a key, before it is reduced to a bucket: ``mod`` uses the
    number itself; ``charSum`` adds the code points of its characters."""
    return key if rule == "mod" else sum(ord(c) for c in key)


def _reduce_hash_table(state: State, op: str, args: Args) -> State:
    key = args["key"]
    problem = _key_problem(state, key)
    if problem:
        raise StructureError(problem)
    buckets = [list(chain) for chain in state["buckets"]]
    hashed = hash_value(state["hash"], key)
    bucket = hashed % len(buckets)
    chain = buckets[bucket]
    where = chain.index(key) if key in chain else None
    if op == "insert":
        if where is not None:
            raise StructureError(f"key {_show(key)} is already in the hash table")
        if sum(len(c) for c in buckets) >= MAX_ITEMS["hashTable"]:
            raise StructureError(f"the hash table is full ({MAX_ITEMS['hashTable']} keys)")
        collision = bool(chain)
        chain.append(key)
        last = {"op": "insert", "key": key, "hash": hashed, "bucket": bucket, "position": len(chain) - 1, "collision": collision}
        return state | {"buckets": buckets, "last": last}
    if op == "lookup":
        last = {
            "op": "lookup", "key": key, "hash": hashed, "bucket": bucket, "position": where,
            "found": where is not None, "probes": len(chain) if where is None else where + 1,
        }
        return state | {"buckets": buckets, "last": last}
    if where is None:  # remove
        raise StructureError(f"key {_show(key)} is not in the hash table")
    chain.pop(where)
    return state | {"buckets": buckets, "last": {"op": "remove", "key": key, "hash": hashed, "bucket": bucket, "position": where}}


def _children(nodes: list[dict]) -> dict[Any, dict[str, Any]]:
    """Left and right child keys of each node, from the parent links."""
    kids: dict[Any, dict[str, Any]] = {n["key"]: {"left": None, "right": None} for n in nodes}
    for node in nodes:
        parent = node["parent"]
        if parent is not None:
            kids[parent]["left" if node["key"] < parent else "right"] = node["key"]
    return kids


def _layout(root: Any, kids: dict[Any, dict[str, Any]], parents: dict[Any, Any]) -> list[dict]:
    """Positions: ``depth`` (0 for the root) and ``slot`` (in-order index, so the tree reads left to right)."""
    placed: list[dict] = []

    def walk(key: Any, depth: int) -> None:
        if key is None:
            return
        walk(kids[key]["left"], depth + 1)
        placed.append({"key": key, "parent": parents[key], "depth": depth, "slot": len(placed)})
        walk(kids[key]["right"], depth + 1)

    walk(root, 0)
    return placed


def _search(nodes: list[dict], key: int) -> tuple[list[int], bool]:
    """Keys visited from the root while looking for ``key``, and whether it was found."""
    if not nodes:
        return [], False
    kids = _children(nodes)
    current: Any = next(n["key"] for n in nodes if n["parent"] is None)
    path: list[int] = []
    while current is not None:
        path.append(current)
        if key == current:
            return path, True
        current = kids[current]["left" if key < current else "right"]
    return path, False


def _reduce_tree(state: State, op: str, args: Args) -> State:
    key = args["key"]
    problem = _key_problem(state, key)
    if problem:
        raise StructureError(problem)
    nodes = state["nodes"]
    path, found = _search(nodes, key)
    if op == "lookup":
        return state | {"last": {"op": "lookup", "key": key, "path": path, "found": found}}
    if op == "highlight":
        if not found:
            raise StructureError(f"key {key} is not in the tree")
        return state | {"last": {"op": "highlight", "key": key, "path": path}}
    if found:
        raise StructureError(f"key {key} is already in the tree")
    if len(nodes) >= MAX_ITEMS["tree"]:
        raise StructureError(f"the tree is full ({MAX_ITEMS['tree']} nodes)")
    if len(path) + 1 > MAX_TREE_DEPTH:
        raise StructureError(f"inserting {key} would make the tree more than {MAX_TREE_DEPTH} levels deep")
    parents = {n["key"]: n["parent"] for n in nodes} | {key: path[-1] if path else None}
    kids = _children(nodes) | {key: {"left": None, "right": None}}
    if path:
        kids[path[-1]] = kids[path[-1]] | {"left" if key < path[-1] else "right": key}
    root = path[0] if path else key
    return state | {"nodes": _layout(root, kids, parents), "last": {"op": "insert", "key": key, "path": path + [key]}}


_REDUCERS: dict[str, Callable[[State, str, Args], State]] = {
    "array": _reduce_array,
    "stack": _reduce_stack,
    "queue": _reduce_queue,
    "hashTable": _reduce_hash_table,
    "tree": _reduce_tree,
}


def reduce(state: State, op: str, args: Args) -> State:
    """Apply one operation to a structure state. Pure: ``state`` is not changed; the result shares nothing with it."""
    kind = state["kind"]
    if op == "clear":
        return copy.deepcopy(state) | {"last": None}
    if op not in OPERATIONS[kind]:
        raise StructureError(f"{_NAMES[kind]} does not support {op}; it supports {', '.join(OPERATIONS[kind])}")
    return copy.deepcopy(_REDUCERS[kind](state, op, args))


# ---------------------------------------------------------------------------
# Arguments of an action, as a client writes them
# ---------------------------------------------------------------------------

def parse_args(params: dict, op: str, raw: Any) -> tuple[Args, Problems]:
    """Check an action's params without the structure's current contents. Problems are
    ``(field, message)`` pairs; an empty field means the params as a whole."""
    kind = params["kind"]
    if op in ("pop", "dequeue", "peek", "clear"):
        if raw is None or raw == {}:
            return {}, []
        return {}, [("", f"{op} takes no params")]
    needs = {"set": "index and params.value", "swap": "indexes", "compare": "indexes", "highlight": "indexes",
             "push": "value", "enqueue": "value"}.get(op, "key")
    if op == "highlight" and kind == "tree":
        needs = "key"
    if not isinstance(raw, dict):
        return {}, [("", f"{op} needs params.{needs}")]
    allowed = {"set": {"index", "value"}, "swap": {"indexes"}, "compare": {"indexes"}, "highlight": {"indexes"},
               "push": {"value"}, "enqueue": {"value"}}.get(op, {"key"})
    if op == "highlight" and kind == "tree":
        allowed = {"key"}
    problems: Problems = [(key, "unknown field") for key in raw if key not in allowed]
    args: Args = {}
    if "index" in allowed:
        if _is_int(raw.get("index")):
            args["index"] = raw["index"]
        else:
            problems.append(("index", "index must be a whole number"))
    if "value" in allowed:
        problem = item_problem(raw.get("value"))
        if problem:
            problems.append(("value", problem))
        else:
            args["value"] = _clean(raw["value"])
    if "indexes" in allowed:
        indexes = raw.get("indexes")
        exact = op in ("swap", "compare")
        valid = isinstance(indexes, list) and all(_is_int(i) for i in indexes)
        if exact and not (valid and len(indexes) == 2):
            problems.append(("indexes", "indexes must be two whole numbers"))
        elif not exact and not (valid and 1 <= len(indexes) <= MAX_ITEMS["array"]):
            problems.append(("indexes", f"indexes must list 1 to {MAX_ITEMS['array']} whole numbers"))
        elif len(set(indexes)) != len(indexes) and not exact:
            problems.append(("indexes", "indexes must not repeat"))
        else:
            args["indexes"] = list(indexes)
    if "key" in allowed:
        problem = _key_problem(params, raw.get("key"))
        if problem:
            problems.append(("key", problem))
        else:
            args["key"] = _clean(raw["key"])
    return ({} if problems else args), problems
