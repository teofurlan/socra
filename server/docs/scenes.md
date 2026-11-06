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
| `code` | `code` (required, shown verbatim), `language` (syntax colours only) | `focus` with `{ "lines": [start, end] }` (1-based, inclusive, inside the code); `clear` removes the focus. The page outlines the focused lines with particles. |
| `headline` | `text` (required, one line, at most 24 characters after trimming) | `set` with `{ "text": "..." }` replaces the words. |
| `shape` | `shape` (`cube`, `cylinder`, `cone`, `sphere`, `torus`), `wireframe` (optional boolean) | `rotate` with `{ "rx"?, "ry"?, "rz"? }` (finite numbers, in turns; at least one is required), `reset` (restores rotation to 0), `set` with `{ "shape"?, "wireframe"? }` (at least one is required). Shapes have no colour param; the page draws them with the state palette. |
| `diagram` | `nodes` (required, 1 to 25: `{ id, label, group? }`), `edges` (`{ from, to, label?, hidden? }`, at most 60), `direction` (`LR` by default, or `TB`) | `highlight` / `dim` with `{ "nodes": [ids] }` (each replaces its previous set; a node is never both); `reveal` with `{ "from", "to" }` draws an edge declared `hidden`; `trace` with `{ "path": [ids] }` animates along existing edges in order and reveals them; `annotate` with `{ "node", "text" }` adds a note beside a node; `clear` drops highlight, dim, trace and notes (revealed edges stay). |

### Presenting with particles

The page's particle field takes part in a scene. While a `headline` is visible, the
particles leave the voice shape and assemble its words in the voice stage, still pulsing
and colouring with who is speaking; the words are also in the page for screen readers.
Only the first visible headline is drawn. While a `code` object has a focus, a few
particles outline the focused lines in the code panel and follow them as it scrolls.
A visible `shape` is assembled from the particles as a solid and takes the stage over a
headline: while a shape is visible, the headline is not drawn.
A `diagram` is crisp SVG in the content panel; the particles only point at it: while nodes
are highlighted they outline them, and while a path is traced they follow its edges.
Everything that has to be read stays crisp text: code, labels and what is being said.

### Diagrams

The page lays the diagram out (dagre); you never provide coordinates. Rules:

- Node ids are unique; labels are one line, at most 40 characters; `group` (at most 24) tints
  nodes of the same group; edge labels hold at most 30 characters.
- Edges are directed, join two declared and different nodes, and a `from`/`to` pair appears once
  (that pair is how `reveal` and `trace` name an edge). Cycles are fine.
- A `trace` path needs at least two nodes, and each consecutive pair must be an existing edge in
  its direction (`no edge a -> b in this diagram` otherwise).
- Diagrams of 3 to 15 nodes read best; 25 is the cap. `LR` suits request paths and call flows;
  the page lays a wide `LR` diagram out top to bottom on a narrow screen when that reads better.
- Notes (`annotate`) are one line, at most 60 characters; a second note on a node replaces its text.

Example ([`scene.diagram.example.json`](scene.diagram.example.json)):

```json
{
  "objects": [{ "id": "flow", "primitive": "diagram", "params": {
    "nodes": [{ "id": "browser", "label": "Browser" }, { "id": "api", "label": "API" }, { "id": "db", "label": "Database" }],
    "edges": [{ "from": "browser", "to": "api", "label": "GET /items" }, { "from": "api", "to": "db", "hidden": true }]
  } }],
  "cues": [
    { "at": "intro", "do": [{ "object": "flow", "action": "highlight", "params": { "nodes": ["browser"] } }] },
    { "at": "query", "do": [{ "object": "flow", "action": "trace", "params": { "path": ["browser", "api", "db"] } }] }
  ]
}
```

### Choosing what to show

- Use `shape` to show a body (cube, cylinder, cone, sphere, torus).
- Use a `headline` only for one key concept worth highlighting, not as a caption for every step.
- Use a `diagram` for call flows, request paths and system designs (boxes and arrows); not for
  data structures (a separate primitive covers those).
- Never draw figures as ASCII art in a code block; code blocks are for real code.
- Narration belongs inside the steps: after `present` returns, do not describe what is on screen.

New primitives (data structures, images) register their params, actions
and state in `PRIMITIVES` without changing the scene contract.

## When a scene ends

A scene that plays to the end returns `{"status": "completed", "steps": N, "note": "..."}`.
The `note` tells the agent the scene is over, that its last step (figures and panel) stays
on the page until the user speaks, and that it must not narrate the scene as if it were
appearing now; a brief follow-up question is fine. A stopped scene returns
`{"status": "stopped", ...}` and its figures clear at once.

## Validation

The whole scene is checked before anything is shown or spoken. An invalid scene returns
`{"status": "invalid", "errors": [{"path": "cues[0].do[1].params.lines", "message": "..."}]}`
with every problem found; fix them and call again.

`explain(code, language, steps)` is the same thing with one `code` object: each step
focuses its lines, or clears the focus when it has none.
