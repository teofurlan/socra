"""The data structure reducers: pure, deterministic, one per kind (issue #69, S3-S5, S7, S9)."""
from __future__ import annotations

import copy

import pytest

from socra_server.domain.structures import (
    MAX_ITEMS,
    MAX_TREE_DEPTH,
    OPERATIONS,
    StructureError,
    initial_state,
    parse_args,
    reduce,
)


def make(kind, items=(), **options):
    params = {"kind": kind, "items": list(items)} | options
    return initial_state(params)


def run(state, *ops):
    for op, args in ops:
        state = reduce(state, op, args)
    return state


# ---------------------------------------------------------------------------
# array
# ---------------------------------------------------------------------------

def test_array_set_replaces_one_cell_and_reports_what_it_replaced():
    state = reduce(make("array", [5, 3, 8]), "set", {"index": 1, "value": 9})
    assert state["items"] == [5, 9, 8]
    assert state["last"] == {"op": "set", "index": 1, "value": 9, "previous": 3}


def test_array_swap_exchanges_two_cells():
    state = reduce(make("array", [5, 3, 8]), "swap", {"indexes": [0, 2]})
    assert state["items"] == [8, 3, 5]
    assert state["last"] == {"op": "swap", "indexes": [0, 2]}


def test_array_compare_reports_the_order_without_changing_the_array():
    start = make("array", [5, 3, 8])
    state = reduce(start, "compare", {"indexes": [0, 1]})
    assert state["items"] == [5, 3, 8]
    assert state["last"] == {"op": "compare", "indexes": [0, 1], "result": "greater"}
    assert reduce(start, "compare", {"indexes": [1, 0]})["last"]["result"] == "less"
    assert reduce(make("array", [4, 4]), "compare", {"indexes": [0, 1]})["last"]["result"] == "equal"
    assert reduce(make("array", ["b", "a"]), "compare", {"indexes": [0, 1]})["last"]["result"] == "greater"


def test_array_highlight_marks_indexes():
    state = reduce(make("array", [1, 2, 3]), "highlight", {"indexes": [2, 0]})
    assert state["last"] == {"op": "highlight", "indexes": [2, 0]}


@pytest.mark.parametrize(
    ("op", "args", "fragment"),
    [
        ("set", {"index": 3, "value": 1}, "index 3 is outside the array, which has 3 items"),
        ("set", {"index": -1, "value": 1}, "index -1 is outside"),
        ("swap", {"indexes": [0, 5]}, "index 5 is outside"),
        ("swap", {"indexes": [1, 1]}, "two different indexes"),
        ("compare", {"indexes": [0, 9]}, "index 9 is outside"),
        ("highlight", {"indexes": [0, 3]}, "index 3 is outside"),
    ],
)
def test_array_rejects_indexes_that_do_not_exist(op, args, fragment):
    with pytest.raises(StructureError, match=fragment):
        reduce(make("array", [1, 2, 3]), op, args)


def test_array_compare_rejects_numbers_against_text():
    with pytest.raises(StructureError, match="cannot compare"):
        reduce(make("array", [1, "a"]), "compare", {"indexes": [0, 1]})


# ---------------------------------------------------------------------------
# stack and queue
# ---------------------------------------------------------------------------

def test_stack_is_last_in_first_out():
    state = run(make("stack"), ("push", {"value": 1}), ("push", {"value": "two"}))
    assert state["items"] == [1, "two"]
    assert state["last"] == {"op": "push", "index": 1, "value": "two"}
    peeked = reduce(state, "peek", {})
    assert peeked["items"] == [1, "two"]
    assert peeked["last"] == {"op": "peek", "index": 1, "value": "two"}
    popped = reduce(state, "pop", {})
    assert popped["items"] == [1]
    assert popped["last"] == {"op": "pop", "index": 1, "value": "two"}


def test_queue_is_first_in_first_out():
    state = run(make("queue", [1, 2]), ("enqueue", {"value": 3}))
    assert state["items"] == [1, 2, 3]
    assert state["last"] == {"op": "enqueue", "index": 2, "value": 3}
    served = reduce(state, "dequeue", {})
    assert served["items"] == [2, 3]
    assert served["last"] == {"op": "dequeue", "index": 0, "value": 1}
    assert reduce(state, "peek", {})["last"] == {"op": "peek", "index": 0, "value": 1}


@pytest.mark.parametrize(
    ("kind", "op", "fragment"),
    [
        ("stack", "pop", "cannot pop an empty stack"),
        ("stack", "peek", "cannot peek an empty stack"),
        ("queue", "dequeue", "cannot dequeue from an empty queue"),
        ("queue", "peek", "cannot peek an empty queue"),
    ],
)
def test_stack_and_queue_reject_reading_when_empty(kind, op, fragment):
    with pytest.raises(StructureError, match=fragment):
        reduce(make(kind), op, {})


@pytest.mark.parametrize(("kind", "op"), [("stack", "push"), ("queue", "enqueue")])
def test_stack_and_queue_reject_growing_past_their_cap(kind, op):
    full = make(kind, list(range(MAX_ITEMS[kind])))
    with pytest.raises(StructureError, match=f"{kind} is full"):
        reduce(full, op, {"value": 1})


# ---------------------------------------------------------------------------
# hash table
# ---------------------------------------------------------------------------

def test_mod_rule_puts_a_whole_number_in_bucket_key_mod_buckets():
    state = make("hashTable", buckets=5, hash="mod")
    state = reduce(state, "insert", {"key": 12})
    assert state["buckets"] == [[], [], [12], [], []]
    assert state["last"] == {"op": "insert", "key": 12, "hash": 12, "bucket": 2, "position": 0, "collision": False}


def test_a_collision_chains_the_key_after_the_ones_already_in_its_bucket():
    state = run(make("hashTable", buckets=5), ("insert", {"key": 12}), ("insert", {"key": 7}), ("insert", {"key": 17}))
    assert state["buckets"][2] == [12, 7, 17]
    assert state["last"]["collision"] is True
    assert state["last"]["position"] == 2


def test_negative_keys_still_land_in_a_valid_bucket():
    state = reduce(make("hashTable", buckets=5), "insert", {"key": -3})
    assert state["last"]["bucket"] == 2


def test_charsum_rule_adds_the_code_points_of_a_string():
    state = make("hashTable", buckets=4, hash="charSum")
    state = reduce(state, "insert", {"key": "ab"})  # 97 + 98 = 195, 195 mod 4 = 3
    assert state["last"] == {"op": "insert", "key": "ab", "hash": 195, "bucket": 3, "position": 0, "collision": False}
    state = reduce(state, "insert", {"key": "ba"})  # same letters, same sum: collides
    assert state["buckets"][3] == ["ab", "ba"]
    assert state["last"]["collision"] is True


def test_initial_contents_are_inserted_in_order_with_the_chosen_rule():
    state = make("hashTable", [12, 7, 3], buckets=5)
    assert state["buckets"] == [[], [], [12, 7], [3], []]
    assert state["last"] is None


def test_lookup_walks_the_chain_and_reports_found_with_the_probes():
    state = make("hashTable", [12, 7, 17], buckets=5)
    hit = reduce(state, "lookup", {"key": 17})
    assert hit["buckets"] == state["buckets"]
    assert hit["last"] == {"op": "lookup", "key": 17, "hash": 17, "bucket": 2, "position": 2, "found": True, "probes": 3}


def test_lookup_of_a_missing_key_is_a_result_not_an_error():
    state = make("hashTable", [12, 7], buckets=5)
    miss = reduce(state, "lookup", {"key": 22})
    assert miss["last"] == {"op": "lookup", "key": 22, "hash": 22, "bucket": 2, "position": None, "found": False, "probes": 2}
    empty = reduce(state, "lookup", {"key": 4})
    assert empty["last"]["found"] is False and empty["last"]["probes"] == 0


def test_remove_takes_the_key_out_of_its_chain():
    state = reduce(make("hashTable", [12, 7, 17], buckets=5), "remove", {"key": 7})
    assert state["buckets"][2] == [12, 17]
    assert state["last"] == {"op": "remove", "key": 7, "hash": 7, "bucket": 2, "position": 1}


@pytest.mark.parametrize(
    ("op", "key", "fragment"),
    [
        ("remove", 99, "key 99 is not in the hash table"),
        ("insert", 12, "key 12 is already in the hash table"),
        ("insert", "a", "mod rule needs whole-number keys"),
        ("lookup", "a", "mod rule needs whole-number keys"),
    ],
)
def test_hash_table_rejects_impossible_operations(op, key, fragment):
    with pytest.raises(StructureError, match=fragment):
        reduce(make("hashTable", [12], buckets=5), op, {"key": key})


def test_charsum_rejects_numbers_and_the_table_rejects_growing_past_its_cap():
    with pytest.raises(StructureError, match="charSum rule needs text keys"):
        reduce(make("hashTable", ["a"], hash="charSum"), "insert", {"key": 5})
    full = make("hashTable", list(range(MAX_ITEMS["hashTable"])), buckets=5)
    with pytest.raises(StructureError, match="hash table is full"):
        reduce(full, "insert", {"key": 1000})


# ---------------------------------------------------------------------------
# tree
# ---------------------------------------------------------------------------

def positions(state):
    return {n["key"]: (n["depth"], n["slot"], n["parent"]) for n in state["nodes"]}


def test_a_binary_search_tree_places_smaller_keys_left_and_larger_right():
    state = make("tree", [8, 3, 10, 1, 6])
    assert positions(state) == {
        1: (2, 0, 3),
        3: (1, 1, 8),
        6: (2, 2, 3),
        8: (0, 3, None),
        10: (1, 4, 8),
    }
    assert [n["key"] for n in state["nodes"]] == [1, 3, 6, 8, 10]  # in-order, so slots read left to right


def test_insert_reports_the_path_to_the_new_node_and_recomputes_positions():
    state = reduce(make("tree", [8, 3, 10]), "insert", {"key": 6})
    assert state["last"] == {"op": "insert", "key": 6, "path": [8, 3, 6]}
    assert positions(state)[6] == (2, 1, 3)
    assert positions(state)[8] == (0, 2, None)


def test_lookup_reports_the_visited_path_and_whether_it_was_found():
    state = make("tree", [8, 3, 10, 1, 6])
    assert reduce(state, "lookup", {"key": 6})["last"] == {"op": "lookup", "key": 6, "path": [8, 3, 6], "found": True}
    assert reduce(state, "lookup", {"key": 7})["last"] == {"op": "lookup", "key": 7, "path": [8, 3, 6], "found": False}
    assert reduce(make("tree"), "lookup", {"key": 1})["last"] == {"op": "lookup", "key": 1, "path": [], "found": False}


def test_tree_highlight_marks_the_path_to_an_existing_key():
    state = reduce(make("tree", [8, 3, 10]), "highlight", {"key": 3})
    assert state["last"] == {"op": "highlight", "key": 3, "path": [8, 3]}


@pytest.mark.parametrize(
    ("op", "key", "fragment"),
    [
        ("insert", 3, "key 3 is already in the tree"),
        ("highlight", 99, "key 99 is not in the tree"),
    ],
)
def test_tree_rejects_impossible_operations(op, key, fragment):
    with pytest.raises(StructureError, match=fragment):
        reduce(make("tree", [8, 3]), op, {"key": key})


def test_tree_rejects_growing_deeper_than_its_cap_or_past_its_size():
    chain = list(range(1, MAX_TREE_DEPTH + 1))
    with pytest.raises(StructureError, match=f"more than {MAX_TREE_DEPTH} levels"):
        reduce(make("tree", chain), "insert", {"key": MAX_TREE_DEPTH + 1})
    with pytest.raises(StructureError, match="tree is full"):
        reduce(make("tree", [50, 25, 75, 12, 37, 62, 87, 6, 18, 31, 43, 56][: MAX_ITEMS["tree"]]), "insert", {"key": 70})


# ---------------------------------------------------------------------------
# Every reducer is pure and deterministic
# ---------------------------------------------------------------------------

CASES = [
    (make("array", [3, 1, 2]), "swap", {"indexes": [0, 1]}),
    (make("stack", [1]), "push", {"value": 2}),
    (make("queue", [1, 2]), "dequeue", {}),
    (make("hashTable", [1, 6], buckets=5), "insert", {"key": 11}),
    (make("tree", [5, 2]), "insert", {"key": 9}),
]


@pytest.mark.parametrize(("state", "op", "args"), CASES)
def test_a_reducer_does_not_mutate_its_input_and_gives_the_same_result_twice(state, op, args):
    before = copy.deepcopy(state)
    first = reduce(state, op, args)
    assert state == before
    assert reduce(state, op, args) == first
    first["last"]["tampered"] = True
    assert "tampered" not in reduce(state, op, args)["last"]


def test_clear_drops_the_last_operation_of_any_kind():
    for state, op, args in CASES:
        assert reduce(reduce(state, op, args), "clear", {})["last"] is None


def test_every_kind_has_its_operations_and_a_reducer_for_each():
    assert {k: set(v) for k, v in OPERATIONS.items()} == {
        "array": {"set", "swap", "compare", "highlight"},
        "stack": {"push", "pop", "peek"},
        "queue": {"enqueue", "dequeue", "peek"},
        "hashTable": {"insert", "lookup", "remove"},
        "tree": {"insert", "lookup", "highlight"},
    }


def test_an_operation_of_another_kind_is_rejected():
    with pytest.raises(StructureError, match="stack does not support enqueue"):
        reduce(make("stack"), "enqueue", {"value": 1})


# ---------------------------------------------------------------------------
# Initial contents and argument parsing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("params", "fragment"),
    [
        ({"kind": "array", "items": []}, "array needs at least one item"),
        ({"kind": "stack", "items": list(range(11))}, "at most 10"),
        ({"kind": "stack", "items": [1.5]}, "whole number or text"),
        ({"kind": "stack", "items": [True]}, "whole number or text"),
        ({"kind": "stack", "items": ["x" * 9]}, "at most 8 characters"),
        ({"kind": "stack", "items": ["a\nb"]}, "one line"),
        ({"kind": "stack", "items": [10000]}, "between -9999 and 9999"),
        ({"kind": "tree", "items": ["a"]}, "tree keys must be whole numbers"),
        ({"kind": "tree", "items": [1, 1]}, "key 1 is already in the tree"),
        ({"kind": "hashTable", "items": [1, 1]}, "already in the hash table"),
        ({"kind": "hashTable", "items": ["a"], "hash": "mod"}, "mod rule needs whole-number keys"),
    ],
)
def test_bad_initial_contents_are_rejected(params, fragment):
    with pytest.raises(StructureError, match=fragment):
        initial_state(params)


def test_parse_args_reports_each_problem_with_its_field():
    assert parse_args({"kind": "array"}, "set", {"index": "a", "value": 1}) == ({}, [("index", "index must be a whole number")])
    args, problems = parse_args({"kind": "array"}, "swap", {"indexes": [1]})
    assert problems == [("indexes", "indexes must be two whole numbers")]
    args, problems = parse_args({"kind": "stack"}, "push", None)
    assert problems == [("", "push needs params.value")]
    assert parse_args({"kind": "stack"}, "push", {"value": 1, "x": 2})[1] == [("x", "unknown field")]
    assert parse_args({"kind": "stack"}, "pop", {"x": 1})[1] == [("", "pop takes no params")]
    assert parse_args({"kind": "hashTable", "hash": "mod"}, "insert", {"key": "a"})[1] == [("key", "the mod rule needs whole-number keys")]
    args, problems = parse_args({"kind": "array"}, "highlight", {"indexes": [0, 2]})
    assert (args, problems) == ({"indexes": [0, 2]}, [])
