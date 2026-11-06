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
| `structure` | `kind` (`array`, `stack`, `queue`, `hashTable`, `tree`), `items` (initial contents), `buckets` and `hash` (hash table only) | Operations by kind, see [Data structures](#data-structures); `clear` drops the mark of the last operation. |

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
A `structure` is crisp SVG too: while an operation's result is on screen, a few particles outline the
element it touched (a cell, a chain entry, the nodes of a search path).
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
  the page keeps the direction you asked for whenever the diagram fits at full size, and lays a
  wide `LR` diagram out top to bottom only when it would have to shrink (or scroll sideways) and
  the other direction fits clearly better.
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

### Data structures

The `structure` primitive draws an array, stack, queue, hash table or binary search tree whose
states **the runtime computes**: the scene names operations and the page shows what they did, so a
picture can never contradict the logic being explained. Each kind has one pure, deterministic reducer
(`socra_server/domain/structures.py`); the scene's state after each step carries the contents plus
`last`, what the latest operation did, which the page animates inside that step.

| Kind | Operations (`params`) | `last` carries |
| --- | --- | --- |
| `array` | `set` `{index, value}`; `swap` `{indexes: [i, j]}`; `compare` `{indexes: [i, j]}`; `highlight` `{indexes: [...]}` | the indexes, the replaced value, the order of a compare (`less`, `equal`, `greater`) |
| `stack` | `push` `{value}`; `pop`; `peek` | the index and the value pushed, popped or seen |
| `queue` | `enqueue` `{value}`; `dequeue`; `peek` | the index and the value (front is index 0) |
| `hashTable` | `insert` `{key}`; `lookup` `{key}`; `remove` `{key}` | the hash, the `bucket`, the `position` in its chain, `collision` (insert), `found` and `probes` (lookup) |
| `tree` | `insert` `{key}`; `lookup` `{key}`; `highlight` `{key}` | the `path` of keys from the root, and `found` (lookup) |

Rules:

- **Values**: a whole number between -9999 and 9999, or one line of text of at most 8 characters. A
  tree takes whole numbers (smaller keys go left, larger right).
- **Hash rules** (`hash`, for a hash table): `mod` (default) takes whole-number keys and uses the key
  itself, so negatives still land in a valid bucket; `charSum` takes text keys and adds the code points
  of their characters (`"ab"` is 97 + 98 = 195). The hash is then reduced modulo the bucket count
  (`buckets`, 2 to 8, default 5). Keys landing in the same bucket are **chained** in insertion order and
  drawn as a chain; an `insert` into a non-empty bucket reports `collision: true`.
- **Tree positions** are computed by the runtime (`depth` from the root, `slot` in reading order) and
  the page draws them; you never provide coordinates.
- **Caps**: at most 12 items (10 in a stack or a queue; 12 keys in a hash table, 12 nodes in a tree),
  a tree at most 5 levels deep. `items` may be empty for everything but an array (at least 1).
- **Impossible operations are rejected by validation, before anything is spoken**: every cue is
  simulated in step order, so `pop` on an empty stack, `dequeue` on an empty queue, an index outside
  an array, a full structure, `insert` of a key already present, `remove` of a missing key and tree
  `highlight` of a missing key are reported as `cues[i].do[j]` with the step id. After one failed
  operation the rest of that object is not simulated, since it would depend on it.
- **A lookup of a missing key is a result, not an error**: the state says `found: false` and the page
  shows the walk that failed. Use `highlight` on a tree only for keys that exist.
- An operation of another kind (`push` on an array) is rejected with the list the kind supports.
- Long hash chains scroll sideways rather than shrinking the text.

Example ([`scene.structure.example.json`](scene.structure.example.json) uses every kind):

```json
{
  "objects": [{ "id": "table", "primitive": "structure", "params": { "kind": "hashTable", "buckets": 5, "hash": "mod", "items": [12, 3] } }],
  "cues": [
    { "at": "collide", "do": [{ "object": "table", "action": "insert", "params": { "key": 17 } }] },
    { "at": "find", "do": [{ "object": "table", "action": "lookup", "params": { "key": 17 } }] }
  ]
}
```

Other kinds: `{"kind": "stack", "items": [1, 2]}` with `push` / `pop` / `peek`;
`{"kind": "queue", "items": ["a"]}` with `enqueue` / `dequeue`; `{"kind": "array", "items": [5, 3, 8]}` with
`swap` / `compare`; `{"kind": "tree", "items": [8, 3, 10]}` with `insert` / `lookup`.

### Choosing what to show

- Use `shape` to show a body (cube, cylinder, cone, sphere, torus).
- Use a `headline` only for one key concept worth highlighting, not as a caption for every step.
- Use a `diagram` for call flows, request paths and system designs (boxes and arrows); not for
  data structures.
- Use a `structure` to teach an array, stack, queue, hash table or binary search tree, naming
  operations and letting the page compute their effect; not for general graphs (use a `diagram`).
- Never draw figures as ASCII art in a code block; code blocks are for real code.
- Narration belongs inside the steps: after `present` returns, do not describe what is on screen.

New primitives (images, ...) register their params, actions
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
