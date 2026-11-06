/**
 * The structure object of a scene (array, stack, queue, hash table, binary search tree), read
 * defensively from its params and its state in the current step. The server computes every state,
 * including `last`, what the latest operation did; the page only draws it.
 */
import type { ObjectState, SceneObject, SceneState } from '@/types/scene'

export type StructureKind = 'array' | 'stack' | 'queue' | 'hashTable' | 'tree'
export type Item = number | string
export type HashRule = 'mod' | 'charSum'

export interface TreeNode {
  key: number
  parent: number | null
  /** Levels below the root; the server computes it. */
  depth: number
  /** In-order position, so slots read left to right. */
  slot: number
}

/** What the latest operation did, with the results the server computed. */
export interface LastOp {
  op: string
  index?: number
  indexes?: number[]
  value?: Item
  previous?: Item
  result?: string
  key?: Item
  hash?: number
  bucket?: number
  position?: number | null
  collision?: boolean
  found?: boolean
  probes?: number
  path?: number[]
}

export interface StructureView {
  id: string
  kind: StructureKind
  /** Array, stack (bottom first) and queue (front first). */
  items: Item[]
  /** Hash table: the chain of keys of each bucket. */
  buckets: Item[][]
  hash: HashRule
  /** Tree nodes in reading order. */
  nodes: TreeNode[]
  last: LastOp | null
}

const KINDS: StructureKind[] = ['array', 'stack', 'queue', 'hashTable', 'tree']
/** The most outlines the particles draw at once for one operation. */
export const MAX_TOUCH_OUTLINES = 4

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)
const isItem = (value: unknown): value is Item => (typeof value === 'number' && Number.isFinite(value)) || typeof value === 'string'
const isInt = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value)
const isKind = (value: unknown): value is StructureKind => KINDS.includes(value as StructureKind)

function itemsOf(value: unknown): Item[] {
  return Array.isArray(value) ? value.filter(isItem) : []
}

function bucketsOf(value: unknown): Item[][] {
  return Array.isArray(value) ? value.map(itemsOf) : []
}

function nodesOf(value: unknown): TreeNode[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((raw): TreeNode[] =>
    isRecord(raw) && isInt(raw.key) && isInt(raw.depth) && isInt(raw.slot)
      ? [{ key: raw.key, parent: isInt(raw.parent) ? raw.parent : null, depth: raw.depth, slot: raw.slot }]
      : [],
  )
}

function lastOf(value: unknown): LastOp | null {
  if (!isRecord(value) || typeof value.op !== 'string') return null
  const last: LastOp = { op: value.op }
  if (isInt(value.index)) last.index = value.index
  if (Array.isArray(value.indexes)) last.indexes = value.indexes.filter(isInt)
  if (isItem(value.value)) last.value = value.value
  if (isItem(value.previous)) last.previous = value.previous
  if (typeof value.result === 'string') last.result = value.result
  if (isItem(value.key)) last.key = value.key
  if (isInt(value.hash)) last.hash = value.hash
  if (isInt(value.bucket)) last.bucket = value.bucket
  if (isInt(value.position)) last.position = value.position
  else if (value.position === null) last.position = null
  if (typeof value.collision === 'boolean') last.collision = value.collision
  if (typeof value.found === 'boolean') last.found = value.found
  if (isInt(value.probes)) last.probes = value.probes
  if (Array.isArray(value.path)) last.path = value.path.filter(isInt)
  return last
}

/** The structure of a state record, or of the object's initial one (before the first step speaks). */
function viewOf(object: SceneObject, source: Record<string, unknown>): StructureView | null {
  const kind = source.kind
  if (!isKind(kind)) return null
  return {
    id: object.id,
    kind,
    items: itemsOf(source.items),
    buckets: bucketsOf(source.buckets),
    hash: source.hash === 'charSum' ? 'charSum' : 'mod',
    nodes: nodesOf(source.nodes),
    last: lastOf(source.last),
  }
}

/** The structure objects to draw right now: those shown (before the first step, those not starting hidden). */
export function visibleStructureViews(objects: SceneObject[], state: SceneState | null): StructureView[] {
  return objects.flatMap((object): StructureView[] => {
    if (object.primitive !== 'structure') return []
    const current: ObjectState | undefined = state?.[object.id]
    if (!(current ? current.visible : !object.hidden)) return []
    const initial = isRecord(object.params.initial) ? object.params.initial : null
    const view = current && isKind(current.kind) ? viewOf(object, current) : initial ? viewOf(object, initial) : null
    return view ? [view] : []
  })
}

/** Identifies the operation, so what draws it plays again only when the operation changes. */
export function lastKey(last: LastOp | null): string {
  return last ? JSON.stringify(last) : ''
}

const show = (value: Item | undefined) => (typeof value === 'string' ? `"${value}"` : String(value))

/** How the hash turned a key into a bucket, in words. */
export function hashLine(view: StructureView, last: LastOp): string {
  const buckets = view.buckets.length
  if (last.key === undefined || last.hash === undefined || last.bucket === undefined) return ''
  const reach = view.hash === 'mod' ? `${show(last.key)} mod ${buckets}` : `charSum(${show(last.key)}) = ${last.hash}, ${last.hash} mod ${buckets}`
  return `${reach} = bucket ${last.bucket}`
}

const ORDER_WORDS: Record<string, string> = { less: '<', equal: '=', greater: '>' }
const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** The latest operation as a short sentence under the drawing; empty before any operation. */
export function captionOf(view: StructureView): string {
  const last = view.last
  if (!last) return ''
  const at = (i: number | undefined) => `[${i}]`
  switch (view.kind) {
    case 'array': {
      const [a, b] = last.indexes ?? []
      if (last.op === 'set') return `set ${at(last.index)} = ${show(last.value)} (was ${show(last.previous)})`
      if (last.op === 'swap') return `swap ${at(a)} and ${at(b)}`
      if (last.op === 'compare') return `compare ${at(a)} ${ORDER_WORDS[last.result ?? ''] ?? '?'} ${at(b)}: ${show(view.items[a])} ${ORDER_WORDS[last.result ?? ''] ?? '?'} ${show(view.items[b])}`
      return `highlight ${(last.indexes ?? []).map(at).join(' ')}`
    }
    case 'stack':
    case 'queue':
      return last.op === 'push' || last.op === 'enqueue' ? `${last.op} ${show(last.value)}` : `${last.op} → ${show(last.value)}`
    case 'hashTable': {
      const how = hashLine(view, last)
      if (last.op === 'insert') {
        const before = last.position ?? 0
        return `insert ${show(last.key)}: ${how}${last.collision ? ` · collision, chained after ${plural(before, 'key')}` : ''}`
      }
      if (last.op === 'lookup') {
        return `lookup ${show(last.key)}: ${how} · ${last.found ? `found after ${plural(last.probes ?? 0, 'probe')}` : `not found after ${plural(last.probes ?? 0, 'probe')}`}`
      }
      return `remove ${show(last.key)}: ${how}`
    }
    case 'tree': {
      const route = (last.path ?? []).join(' → ')
      if (last.op === 'insert') return `insert ${last.key}: ${route}`
      if (last.op === 'lookup') return `lookup ${last.key}: ${route ? `${route}, ` : ''}${last.found ? 'found' : 'not found'}`
      return `path to ${last.key}: ${route}`
    }
  }
}

/**
 * The parts of the drawing the latest operation touched, as the ids the drawing puts in
 * `data-structure-part`: the particles outline them, the drawing marks them. A removed element is no
 * longer drawn and is not listed.
 */
export function touchedParts(view: StructureView): string[] {
  const last = view.last
  if (!last) return []
  switch (view.kind) {
    case 'array':
      return (last.op === 'set' ? [last.index] : (last.indexes ?? [])).flatMap((i) => (i === undefined ? [] : [`cell:${i}`]))
    case 'stack':
    case 'queue':
      return (last.op === 'push' || last.op === 'enqueue' || last.op === 'peek') && last.index !== undefined ? [`cell:${last.index}`] : []
    case 'hashTable': {
      if (last.bucket === undefined) return []
      const hit = last.op !== 'remove' && last.position !== undefined && last.position !== null
      return [hit ? `entry:${last.bucket}:${last.position}` : `bucket:${last.bucket}`]
    }
    case 'tree': {
      const path = last.path ?? []
      return path.slice(-MAX_TOUCH_OUTLINES).map((key) => `node:${key}`)
    }
  }
}

/** The part to outline for a tree path, in walking order (the outlines go to the last nodes of a long path). */
export function pathKeys(view: StructureView): number[] {
  return view.kind === 'tree' ? (view.last?.path ?? []) : []
}

export const TITLES: Record<StructureKind, string> = {
  array: 'Array',
  stack: 'Stack',
  queue: 'Queue',
  hashTable: 'Hash table',
  tree: 'Binary search tree',
}

/** The contents as text, for screen readers: the drawing is an image to them. */
export function summaryOf(view: StructureView): string {
  const title = TITLES[view.kind]
  if (view.kind === 'hashTable') {
    const rows = view.buckets.map((chain, b) => `bucket ${b}: ${chain.length ? chain.join(', ') : 'empty'}`)
    return `${title}, ${view.buckets.length} buckets. ${rows.join('; ')}`
  }
  if (view.kind === 'tree') return `${title}, keys in order: ${view.nodes.map((n) => n.key).join(', ') || 'none'}`
  const order = view.kind === 'stack' ? ' (bottom to top)' : view.kind === 'queue' ? ' (front to back)' : ''
  return `${title}${order}: ${view.items.join(', ') || 'empty'}`
}
