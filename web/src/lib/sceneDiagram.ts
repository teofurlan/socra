/** The diagram object of a scene, read defensively from its params and its state in the current step. */
import { edgeKey, type DiagramDirection, type DiagramEdgeInput, type DiagramNodeInput } from '@/lib/diagramLayout'
import type { ObjectState, SceneObject, SceneState } from '@/types/scene'

export interface DiagramView {
  id: string
  direction: DiagramDirection
  nodes: DiagramNodeInput[]
  edges: DiagramEdgeInput[]
  highlighted: Set<string>
  dimmed: Set<string>
  /** Keys (`from>to`) of the edges that are drawn. */
  revealed: Set<string>
  /** The traced path as node ids, empty when nothing is traced. */
  trace: string[]
  notes: Record<string, string>
}

const isString = (value: unknown): value is string => typeof value === 'string'
const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value)

function nodesOf(value: unknown): DiagramNodeInput[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((raw): DiagramNodeInput[] =>
    isRecord(raw) && isString(raw.id) && isString(raw.label) ? [{ id: raw.id, label: raw.label, group: isString(raw.group) ? raw.group : '' }] : [],
  )
}

function edgesOf(value: unknown, ids: Set<string>): (DiagramEdgeInput & { hidden: boolean })[] {
  if (!Array.isArray(value)) return []
  return value.flatMap((raw) =>
    isRecord(raw) && isString(raw.from) && isString(raw.to) && ids.has(raw.from) && ids.has(raw.to)
      ? [{ from: raw.from, to: raw.to, label: isString(raw.label) ? raw.label : '', hidden: raw.hidden === true }]
      : [],
  )
}

function idList(value: unknown, ids: Set<string>): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => isString(v) && ids.has(v)) : []
}

function revealedOf(current: ObjectState | undefined, edges: (DiagramEdgeInput & { hidden: boolean })[]): Set<string> {
  if (!current || !Array.isArray(current.revealed)) return new Set(edges.filter((e) => !e.hidden).map((e) => edgeKey(e.from, e.to)))
  return new Set(current.revealed.flatMap((e) => (isRecord(e) && isString(e.from) && isString(e.to) ? [edgeKey(e.from, e.to)] : [])))
}

/** The diagram objects to draw right now: those shown (before the first step, those not starting hidden). */
export function visibleDiagramViews(objects: SceneObject[], state: SceneState | null): DiagramView[] {
  return objects.flatMap((object): DiagramView[] => {
    if (object.primitive !== 'diagram') return []
    const current = state?.[object.id]
    if (!(current ? current.visible : !object.hidden)) return []
    const nodes = nodesOf(object.params.nodes)
    if (nodes.length === 0) return []
    const ids = new Set(nodes.map((n) => n.id))
    const edges = edgesOf(object.params.edges, ids)
    const notes: Record<string, string> = {}
    if (isRecord(current?.notes)) {
      for (const [node, text] of Object.entries(current.notes)) if (ids.has(node) && isString(text) && text) notes[node] = text
    }
    return [{
      id: object.id,
      direction: object.params.direction === 'TB' ? 'TB' : 'LR',
      nodes,
      edges: edges.map(({ from, to, label }) => ({ from, to, label })),
      highlighted: new Set(idList(current?.highlighted, ids)),
      dimmed: new Set(idList(current?.dimmed, ids)),
      revealed: revealedOf(current, edges),
      trace: idList(current?.trace, ids),
      notes,
    }]
  })
}
