# Narrated scenes

A scene is a short narrated explanation: what Socra **says**, what it **shows**, and
**cues** that change the picture at the moment a step starts speaking. Showing the words
and the matching picture together is the point; a scene keeps them in sync step by step.

- Schema: [`scene.schema.json`](scene.schema.json) (JSON Schema 2020-12)
- Example: [`scene.example.json`](scene.example.json)
- Rules: `socra_server/domain/scene.py`

## Shape

```json
{
  "version": 1,
  "title": "How a walkthrough is validated",
  "objects": [{ "id": "parser", "primitive": "code", "params": { "code": "...", "language": "python" } }],
  "steps": [
    { "id": "intro", "say": "This function checks every step before anything is spoken." },
    { "id": "loop", "say": "Each step is numbered from one." }
  ],
  "cues": [
    { "at": "intro", "do": [{ "object": "parser", "action": "focus", "params": { "lines": [1, 1] } }] },
    { "at": "loop", "do": [{ "object": "parser", "action": "focus", "params": { "lines": [3, 5] } }] }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `version` | Always `1`. |
| `title` | Shown above the scene. |
| `objects` | What can be shown, each drawn by a primitive. Optional; at most 16. Objects start visible unless `hidden: true`. |
| `steps` | What is said, in order. Each step is synthesized and spoken on its own. At least 1, at most 60. |
| `cues` | Optional. `at` names a step; `do` lists actions applied, in order, when that step starts. At most one cue per step and 16 actions per cue. |

Ids use letters, digits, `.`, `_` or `-` (at most 64 characters) and are unique among
steps and among objects.

## State, not replay

The picture while a step speaks is every cue up to and including that step, applied in
order. A step without a cue keeps the previous picture. The server resolves that state
for each step, so going back, repeating a step or reconnecting the page always shows the
same thing as playing straight through.

## Primitives and actions

Every primitive supports `show` and `hide`. Primitive-specific actions:

| Primitive | Params | Actions |
| --- | --- | --- |
| `code` | `code` (required, shown verbatim), `language` (syntax colours only) | `focus` with `{ "lines": [start, end] }` (1-based, inclusive, inside the code); `clear` removes the focus. |

New primitives (diagrams, call flows, data structures) register their params, actions
and state in `PRIMITIVES` without changing the scene contract.

## Validation

The whole scene is checked before anything is shown or spoken. An invalid scene returns
`{"status": "invalid", "errors": [{"path": "cues[0].do[1].params.lines", "message": "..."}]}`
with every problem found; fix them and call again.

`explain(code, language, steps)` is the same thing with one `code` object: each step
focuses its lines, or clears the focus when it has none.
