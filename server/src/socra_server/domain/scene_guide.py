"""The scene_guide skill: how to author a valid narrated scene, per entry point — no I/O.

``scene_guide(topic)`` returns the authoring rules, the advice for the topic, the format
reference (``SCENE_GUIDE``) and one example scene as compact JSON. Every example is pinned
to be a valid scene by ``tests/test_scene_guide.py``.
"""
from __future__ import annotations

import json
from typing import Any

from socra_server.domain.scene import SCENE_GUIDE
from socra_server.domain.speech import SPEECH_LANGUAGE_NAME

TOPICS = ("code", "concept")

AUTHORING = (
    "Authoring a scene: use 4 to 10 steps, one idea per step. Each say is one or two short "
    f"spoken sentences in {SPEECH_LANGUAGE_NAME}, in plain words, with no markdown. Never read "
    "code symbol by symbol and never spell out file paths: say the file or function name. "
    "Every visual change goes in the cue of the step that talks about it. Show few objects at "
    "once and hide what is no longer discussed. Write the whole scene first, then call present. "
    "If present returns invalid, fix exactly the reported paths and call present once more; if "
    "it is still invalid, explain by voice instead. After present returns completed, do not "
    "describe what was on screen."
)

ADVICE = {
    "code": (
        "Topic code (explain a module, a flow or a function in the user's project): read only "
        "the files you need first. Show the real code with a code object, only the relevant "
        "part, about 30 lines at most and never whole files, and focus the lines each step "
        "talks about. Use a diagram for how modules, components or a request move through the "
        "project, with 3 to 8 nodes named the way the user knows them. A typical scene opens "
        "with the diagram overview, then goes to the key function in code."
    ),
    "concept": (
        "Topic concept (explain a programming concept): use a structure for arrays, stacks, "
        "queues, hash tables (collisions) and binary search trees, naming the operations and "
        "letting the page compute them. Use a diagram for flows and architectures, a shape for "
        "3D bodies, a headline for the one key term, and code only for a short real snippet."
    ),
}

_HANDLER = (
    "def handle(request):\n"
    "    user = authenticate(request)\n"
    "    order = load_order(user, request.order_id)\n"
    "    total = price(order)\n"
    "    save(order, total)\n"
    "    return {\"total\": total}\n"
)

_CODE_EXAMPLE: dict[str, Any] = {
    "version": 1,
    "title": "How a request is handled",
    "objects": [
        {
            "id": "flow",
            "primitive": "diagram",
            "params": {
                "nodes": [
                    {"id": "client", "label": "Client"},
                    {"id": "handler", "label": "Handler"},
                    {"id": "auth", "label": "Auth"},
                    {"id": "db", "label": "Database"},
                ],
                "edges": [
                    {"from": "client", "to": "handler"},
                    {"from": "handler", "to": "auth"},
                    {"from": "handler", "to": "db"},
                ],
            },
        },
        {"id": "src", "primitive": "code", "params": {"code": _HANDLER, "language": "python"}, "hidden": True},
    ],
    "steps": [
        {"id": "overview", "say": "A request goes through three parts of the project."},
        {"id": "entry", "say": "It first reaches the handler."},
        {"id": "auth", "say": "The handler asks auth who is calling."},
        {"id": "code", "say": "Here is the handler function."},
        {"id": "load", "say": "It loads the order for that user."},
        {"id": "save", "say": "Then it prices the order and saves it."},
    ],
    "cues": [
        {"at": "entry", "do": [{"object": "flow", "action": "highlight", "params": {"nodes": ["handler"]}}]},
        {"at": "auth", "do": [{"object": "flow", "action": "trace", "params": {"path": ["handler", "auth"]}}]},
        {
            "at": "code",
            "do": [
                {"object": "flow", "action": "hide"},
                {"object": "src", "action": "show"},
                {"object": "src", "action": "focus", "params": {"lines": [1, 2]}},
            ],
        },
        {"at": "load", "do": [{"object": "src", "action": "focus", "params": {"lines": [3, 3]}}]},
        {"at": "save", "do": [{"object": "src", "action": "focus", "params": {"lines": [4, 5]}}]},
    ],
}

_CONCEPT_EXAMPLE: dict[str, Any] = {
    "version": 1,
    "title": "Hash table collisions",
    "objects": [
        {"id": "term", "primitive": "headline", "params": {"text": "Collision"}, "hidden": True},
        {"id": "table", "primitive": "structure", "params": {"kind": "hashTable", "buckets": 4, "hash": "mod"}},
    ],
    "steps": [
        {"id": "intro", "say": "A hash table puts each key in a bucket chosen by a hash."},
        {"id": "first", "say": "Here the hash is the key modulo four, so five goes to bucket one."},
        {"id": "second", "say": "Nine also lands in bucket one."},
        {"id": "term", "say": "Two keys in the same bucket is a collision."},
        {"id": "chain", "say": "The bucket keeps both keys in a chain."},
        {"id": "find", "say": "To find nine, we go to bucket one and walk its chain."},
    ],
    "cues": [
        {"at": "first", "do": [{"object": "table", "action": "insert", "params": {"key": 5}}]},
        {"at": "second", "do": [{"object": "table", "action": "insert", "params": {"key": 9}}]},
        {"at": "term", "do": [{"object": "term", "action": "show"}]},
        {"at": "chain", "do": [{"object": "term", "action": "hide"}, {"object": "table", "action": "insert", "params": {"key": 13}}]},
        {"at": "find", "do": [{"object": "table", "action": "lookup", "params": {"key": 9}}]},
    ],
}

EXAMPLES: dict[str, dict[str, Any]] = {"code": _CODE_EXAMPLE, "concept": _CONCEPT_EXAMPLE}


def scene_guide(topic: str) -> str:
    """The guide for one entry point: rules, advice, format reference and an example scene."""
    if not topic:
        return f"A topic is required. Valid topics: {', '.join(TOPICS)}."
    if topic not in TOPICS:
        return f"Unknown topic {topic!r}. Valid topics: {', '.join(TOPICS)}."
    example = json.dumps(EXAMPLES[topic], separators=(",", ":"))
    return f"{AUTHORING}\n\n{ADVICE[topic]}\n\nFormat reference: {SCENE_GUIDE}\n\nExample scene:\n{example}"
