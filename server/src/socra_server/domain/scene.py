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
import re
from collections.abc import Callable, Mapping
from typing import Any

from socra_server.domain.walkthrough import Walkthrough

VERSION = 1
MAX_STEPS = 60
MAX_OBJECTS = 16
MAX_ACTIONS_PER_CUE = 16

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_ID_RULE = "ids use letters, digits, '.', '_' or '-', start with a letter or digit, at most 64 characters"

State = dict[str, Any]
Errors = list[dict]


def _error(path: str, message: str) -> dict:
    return {"path": path, "message": message}


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


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

PRIMITIVES: dict[str, Primitive] = {CODE.name: CODE}


def _actions_of(primitive: Primitive) -> dict[str, ActionSpec]:
    return _COMMON_ACTIONS | dict(primitive.actions)


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


def _resolve(objects: tuple[SceneObject, ...], steps: tuple[SceneStep, ...], cues: tuple[Cue, ...]) -> tuple[dict[str, State], ...]:
    by_step = {cue.at: cue for cue in cues}
    by_id = {obj.id: obj for obj in objects}
    state = {
        obj.id: {"visible": not obj.hidden} | PRIMITIVES[obj.primitive].initial_state(obj.params)
        for obj in objects
    }
    states = []
    for step in steps:
        cue = by_step.get(step.id)
        for action in cue.actions if cue else ():
            spec = _actions_of(PRIMITIVES[by_id[action.object].primitive])[action.action]
            state[action.object] = spec.apply(state[action.object], action.params)
        states.append(copy.deepcopy(state))
    return tuple(states)


def _assemble(title: str, objects: tuple[SceneObject, ...], steps: tuple[SceneStep, ...], cues: tuple[Cue, ...]) -> Scene:
    return Scene(VERSION, title, objects, steps, cues, _resolve(objects, steps, cues))


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
    actions = _actions_of(PRIMITIVES[obj.primitive])
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
    return _assemble(title.strip(), tuple(objects), tuple(steps), tuple(cues)), []


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
