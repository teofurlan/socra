/**
 * Geometry of the structure drawings, in SVG user units (one unit is one pixel at scale 1).
 * Pure and deterministic: the same contents and room always give the same picture. Tree
 * positions come from the server (depth and slot); everything else is arithmetic on the contents.
 */
import type { Item, StructureView, TreeNode } from '@/lib/sceneStructure'

export const FONT = 15
export const SMALL_FONT = 13
export const PAD = 10
const CELL_H = 40
const GAP = 4
/** Room under a cell for its index or its front/back label. */
const LABEL_H = 20
const CHAR_W = 9
const MIN_CELL_W = 40
const MAX_CELL_W = 100

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

export interface Drawing {
  width: number
  height: number
}

/** Wide enough for the longest item, so text never leaves its cell. */
export function cellWidth(items: Item[]): number {
  const longest = items.reduce<number>((n, item) => Math.max(n, String(item).length), 1)
  return Math.min(MAX_CELL_W, Math.max(MIN_CELL_W, longest * CHAR_W + 16))
}

export interface RowLayout extends Drawing {
  cells: (Rect & { i: number })[]
  cellW: number
}

/** Cells left to right, wrapping into rows when `room` is narrower than the whole row. */
export function rowLayout(items: Item[], room: number, extra: Item[] = []): RowLayout {
  const cellW = cellWidth([...items, ...extra])
  const count = Math.max(1, items.length)
  const fit = Math.max(1, Math.floor((room - PAD * 2 + GAP) / (cellW + GAP)))
  const cols = Math.min(count, fit)
  const rows = Math.ceil(count / cols)
  const cells = items.map((_, i) => ({
    i,
    x: PAD + (i % cols) * (cellW + GAP),
    y: PAD + Math.floor(i / cols) * (CELL_H + LABEL_H + GAP),
    w: cellW,
    h: CELL_H,
  }))
  return {
    cells,
    cellW,
    width: PAD * 2 + cols * (cellW + GAP) - GAP,
    height: PAD * 2 + rows * (CELL_H + LABEL_H + GAP) - GAP,
  }
}

/** Where slot `index` of a row layout sits, also for a slot beyond the contents (a vanished element). */
export function slotRect(layout: RowLayout, index: number): Rect {
  const known = layout.cells[index]
  if (known) return known
  const first = layout.cells[0] ?? { x: PAD, y: PAD }
  return { x: first.x, y: first.y, w: layout.cellW, h: CELL_H }
}

export interface StackLayout extends Drawing {
  cells: (Rect & { i: number })[]
  cellW: number
  /** Where the element that just left sat, above the top. */
  ghost: Rect
  baseY: number
}

const STACK_LABEL_W = 44

/** Bottom of the stack at the bottom; one spare row above the top for an element coming or going. */
export function stackLayout(items: Item[], extra: Item[] = []): StackLayout {
  const cellW = cellWidth([...items, ...extra])
  const rows = Math.max(1, items.length) + 1
  const rowH = CELL_H - 4 + GAP
  const cells = items.map((_, i) => ({ i, x: PAD, y: PAD + (rows - 1 - i) * rowH, w: cellW, h: CELL_H - 4 }))
  const ghost = { x: PAD, y: PAD + (rows - 1 - items.length) * rowH, w: cellW, h: CELL_H - 4 }
  return {
    cells,
    cellW,
    ghost,
    baseY: PAD + rows * rowH,
    width: PAD * 2 + cellW + STACK_LABEL_W,
    height: PAD * 2 + rows * rowH + 6,
  }
}

export interface HashLayout extends Drawing {
  rows: { b: number; y: number; h: number; entries: (Rect & { p: number })[] }[]
  cellW: number
  labelW: number
  arrow: number
}

const BUCKET_LABEL_W = 36
const ARROW_W = 18

/** One row per bucket: its index, then the chain of keys that landed there. */
export function hashLayout(buckets: Item[][], extra: Item[] = []): HashLayout {
  const cellW = cellWidth([...buckets.flat(), ...extra])
  const longest = Math.max(1, ...buckets.map((b) => b.length))
  const rowH = CELL_H + 6
  const rows = buckets.map((chain, b) => {
    const y = PAD + b * rowH
    return { b, y, h: CELL_H, entries: chain.map((_, p) => ({ p, x: PAD + BUCKET_LABEL_W + p * (cellW + ARROW_W), y, w: cellW, h: CELL_H })) }
  })
  return {
    rows,
    cellW,
    labelW: BUCKET_LABEL_W,
    arrow: ARROW_W,
    width: PAD * 2 + BUCKET_LABEL_W + longest * cellW + (longest - 1) * ARROW_W,
    height: PAD * 2 + Math.max(1, buckets.length) * rowH - 6,
  }
}

export interface TreeLayout extends Drawing {
  nodes: (Rect & { key: number; parent: number | null; cx: number; cy: number })[]
  edges: { from: number; to: number; x1: number; y1: number; x2: number; y2: number }[]
}

const LEVEL_H = 58
const NODE_H = 36

/** Nodes at the slot and depth the server computed: x grows with the slot, y with the depth. */
export function treeLayout(nodes: TreeNode[]): TreeLayout {
  const nodeW = Math.max(NODE_H, cellWidth(nodes.map((n) => n.key)) - 6)
  const step = nodeW + 6
  const depth = nodes.reduce((n, node) => Math.max(n, node.depth), 0)
  const placed = nodes.map((node) => {
    const x = PAD + node.slot * step
    const y = PAD + node.depth * LEVEL_H
    return { key: node.key, parent: node.parent, x, y, w: nodeW, h: NODE_H, cx: x + nodeW / 2, cy: y + NODE_H / 2 }
  })
  const byKey = new Map(placed.map((n) => [n.key, n]))
  const edges = placed.flatMap((n) => {
    const parent = n.parent === null ? undefined : byKey.get(n.parent)
    return parent ? [{ from: parent.key, to: n.key, x1: parent.cx, y1: parent.y + NODE_H, x2: n.cx, y2: n.y }] : []
  })
  return {
    nodes: placed,
    edges,
    width: PAD * 2 + Math.max(1, nodes.length) * step - 6,
    height: PAD * 2 + depth * LEVEL_H + NODE_H,
  }
}

/** Lowest scale at which text stays legible: the base font times this stays at 10 px or more. */
export const MIN_SCALE = 0.8

/**
 * How much to scale a drawing of `natural` size into `room`: never up, never below MIN_SCALE
 * (the viewport scrolls instead, so the text stays legible).
 */
export function fitScale(natural: Drawing, room: Drawing): number {
  if (natural.width <= 0 || natural.height <= 0) return 1
  const wanted = Math.min(1, room.width / natural.width, room.height / natural.height)
  return Math.max(MIN_SCALE, Number.isFinite(wanted) ? wanted : 1)
}

/** A structure laid out for the room it has, tagged by the kind of drawing that uses it. */
export type Laid =
  | { kind: 'array' | 'queue'; layout: RowLayout }
  | { kind: 'stack'; layout: StackLayout }
  | { kind: 'hashTable'; layout: HashLayout }
  | { kind: 'tree'; layout: TreeLayout }

/** What an element that just left (popped, dequeued, removed) was, so the layout leaves room for it. */
const leaver = (view: StructureView): Item[] => {
  const last = view.last
  if (!last || !['pop', 'dequeue', 'remove'].includes(last.op)) return []
  const gone = last.op === 'remove' ? last.key : last.value
  return gone === undefined ? [] : [gone]
}

/** Lays a structure out in `room` pixels of width (rows of cells wrap to it; the rest do not). */
export function layoutOf(view: StructureView, room: number): Laid {
  switch (view.kind) {
    case 'array':
      return { kind: 'array', layout: rowLayout(view.items, room) }
    case 'queue':
      return { kind: 'queue', layout: rowLayout(view.items, room, leaver(view)) }
    case 'stack':
      return { kind: 'stack', layout: stackLayout(view.items, leaver(view)) }
    case 'hashTable':
      return { kind: 'hashTable', layout: hashLayout(view.buckets, leaver(view)) }
    case 'tree':
      return { kind: 'tree', layout: treeLayout(view.nodes) }
  }
}
