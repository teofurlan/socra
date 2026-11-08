/**
 * Pure layout of a diagram: nodes and edges in, boxes and edge polylines out (dagre does the
 * placing). Coordinates are SVG user units with the origin at the top-left; the model never
 * provides any. No DOM, so it can be tested and reused by the particle pointing.
 */
import { Graph, layout } from '@dagrejs/dagre'

export type DiagramDirection = 'TB' | 'LR'

export interface DiagramNodeInput {
  id: string
  label: string
  group: string
}

export interface DiagramEdgeInput {
  from: string
  to: string
  label: string
}

export interface Point {
  x: number
  y: number
}

export interface PlacedNode extends DiagramNodeInput {
  /** The label split over at most two lines. */
  lines: string[]
  /** Top-left corner. */
  x: number
  y: number
  width: number
  height: number
}

export interface PlacedEdge extends DiagramEdgeInput {
  /** `from>to`, the edge's identity in the scene state. */
  key: string
  points: Point[]
  /** Centre of the label box, or null for an edge without a label. */
  labelAt: Point | null
  labelWidth: number
}

export interface DiagramLayout {
  direction: DiagramDirection
  width: number
  height: number
  nodes: PlacedNode[]
  edges: PlacedEdge[]
}

/** Sizes in SVG units: the node font is 14, the edge label font 12. */
export const NODE_FONT = 14
export const EDGE_FONT = 13
const CHAR_WIDTH = 7.7
const EDGE_CHAR_WIDTH = 7.2
const NODE_PAD_X = 16
const LINE_HEIGHT = 18
const NODE_PAD_Y = 11
const MIN_NODE_WIDTH = 84
const WRAP_AT = 22
const EDGE_LABEL_HEIGHT = 18
const MARGIN = 14

export function polylineLength(points: Point[]): number {
  let total = 0
  for (let i = 1; i < points.length; i++) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y)
  return total
}

export function edgeKey(from: string, to: string): string {
  return `${from}>${to}`
}

/** A label on at most two lines of ``max`` characters: at spaces, hard-broken, ellipsized if longer. */
export function wrapLabel(label: string, max: number): string[] {
  const text = label.trim().replace(/\s+/g, ' ')
  if (text.length <= max) return [text]
  const words = text.split(' ')
  const lines: string[] = []
  let line = ''
  for (const word of words) {
    let rest = word
    while (rest.length > max) {
      if (line) { lines.push(line); line = '' }
      lines.push(rest.slice(0, max))
      rest = rest.slice(max)
    }
    if (!line) line = rest
    else if (line.length + 1 + rest.length <= max) line += ` ${rest}`
    else { lines.push(line); line = rest }
  }
  if (line) lines.push(line)
  if (lines.length <= 2) return lines
  const kept = lines.slice(0, 2)
  kept[1] = `${kept[1].slice(0, max - 1).trimEnd()}…`
  return kept
}

export function layoutDiagram(nodes: DiagramNodeInput[], edges: DiagramEdgeInput[], direction: DiagramDirection): DiagramLayout {
  const graph = new Graph({ multigraph: true })
  graph.setGraph({ rankdir: direction, nodesep: 36, ranksep: 44, edgesep: 14, marginx: MARGIN, marginy: MARGIN })
  graph.setDefaultEdgeLabel(() => ({}))
  const lines = new Map<string, string[]>()
  for (const n of nodes) {
    const wrapped = wrapLabel(n.label, WRAP_AT)
    lines.set(n.id, wrapped)
    const longest = Math.max(...wrapped.map((l) => l.length))
    graph.setNode(n.id, {
      width: Math.max(MIN_NODE_WIDTH, Math.ceil(longest * CHAR_WIDTH + NODE_PAD_X * 2)),
      height: wrapped.length * LINE_HEIGHT + NODE_PAD_Y * 2,
    })
  }
  for (const e of edges) {
    const labelWidth = e.label ? Math.ceil(e.label.length * EDGE_CHAR_WIDTH + 10) : 0
    graph.setEdge(e.from, e.to, { width: labelWidth, height: e.label ? EDGE_LABEL_HEIGHT : 0, labelpos: 'c' }, edgeKey(e.from, e.to))
  }
  layout(graph)

  const placedNodes: PlacedNode[] = nodes.map((n) => {
    const g = graph.node(n.id)
    return { ...n, lines: lines.get(n.id) ?? [n.label], x: g.x - g.width / 2, y: g.y - g.height / 2, width: g.width, height: g.height }
  })
  const placedEdges: PlacedEdge[] = edges.map((e) => {
    const g = graph.edge(e.from, e.to, edgeKey(e.from, e.to))
    const labelWidth = e.label ? Math.ceil(e.label.length * EDGE_CHAR_WIDTH + 10) : 0
    const labelAt = e.label && Number.isFinite(g.x) && Number.isFinite(g.y) ? { x: g.x, y: g.y } : null
    return { ...e, key: edgeKey(e.from, e.to), points: (g.points as Point[]).map(({ x, y }) => ({ x, y })), labelAt, labelWidth }
  })

  // Shift everything so the content starts at the margin and measure what was actually used.
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  const grow = (x0: number, y0: number, x1: number, y1: number) => {
    minX = Math.min(minX, x0); minY = Math.min(minY, y0); maxX = Math.max(maxX, x1); maxY = Math.max(maxY, y1)
  }
  for (const n of placedNodes) grow(n.x, n.y, n.x + n.width, n.y + n.height)
  for (const e of placedEdges) {
    for (const p of e.points) grow(p.x, p.y, p.x, p.y)
    if (e.labelAt) grow(e.labelAt.x - e.labelWidth / 2, e.labelAt.y - EDGE_LABEL_HEIGHT / 2, e.labelAt.x + e.labelWidth / 2, e.labelAt.y + EDGE_LABEL_HEIGHT / 2)
  }
  const dx = MARGIN - minX
  const dy = MARGIN - minY
  for (const n of placedNodes) { n.x += dx; n.y += dy }
  for (const e of placedEdges) {
    e.points = e.points.map((p) => ({ x: p.x + dx, y: p.y + dy }))
    if (e.labelAt) e.labelAt = { x: e.labelAt.x + dx, y: e.labelAt.y + dy }
  }
  return { direction, width: maxX - minX + MARGIN * 2, height: maxY - minY + MARGIN * 2, nodes: placedNodes, edges: placedEdges }
}

/** Annotation boxes: one or two lines of the edge font, a fixed gap under their node. */
export const NOTE_LINE = 16
const NOTE_WRAP = 28
const NOTE_CHAR_WIDTH = 6.9
const NOTE_GAP = 6
/** Room kept between a note and the side of the drawing. */
const NOTE_INSET = 2

export interface NoteBox {
  lines: string[]
  x: number
  y: number
  width: number
  height: number
}

export function noteLines(text: string): string[] {
  if (text.length <= NOTE_WRAP) return [text]
  const cut = text.lastIndexOf(' ', NOTE_WRAP)
  const at = cut > 8 ? cut : NOTE_WRAP
  return [text.slice(0, at).trim(), text.slice(at).trim()]
}

/** A note centred under its node, kept inside a drawing ``width`` wide where it fits. */
export function placeNote(node: PlacedNode, text: string, width: number): NoteBox {
  const lines = noteLines(text)
  const boxWidth = Math.ceil(Math.max(...lines.map((l) => l.length)) * NOTE_CHAR_WIDTH + 16)
  const boxHeight = lines.length * NOTE_LINE + 8
  const x = Math.min(Math.max(node.x + node.width / 2 - boxWidth / 2, NOTE_INSET), Math.max(NOTE_INSET, width - boxWidth - NOTE_INSET))
  return { lines, x, y: node.y + node.height + NOTE_GAP, width: boxWidth, height: boxHeight }
}

/**
 * The drawing's size once its visible notes are in: a note past the bottom (a node on the last
 * row) or wider than the drawing grows it; a note that already has room changes nothing.
 */
export function sizeWithNotes(size: { width: number; height: number }, notes: NoteBox[]): { width: number; height: number } {
  let { width, height } = size
  for (const note of notes) {
    width = Math.max(width, note.x + note.width + NOTE_INSET)
    height = Math.max(height, note.y + note.height + MARGIN)
  }
  return { width, height }
}

/** Never enlarge a diagram past this, so a three-node scene does not become giant boxes. */
export const MAX_SCALE = 1.15
/** Below this the labels stop being legible; the panel scrolls instead of shrinking further. */
export const MIN_SCALE = 0.72

export function fitScale(size: { width: number; height: number }, availWidth: number, availHeight: number): number {
  if (size.width <= 0 || size.height <= 0) return 1
  return Math.min(availWidth / size.width, availHeight / size.height, MAX_SCALE)
}

const OTHER: Record<DiagramDirection, DiagramDirection> = { TB: 'LR', LR: 'TB' }
/** The other direction must fit this much better before it replaces the asked one. */
const SWITCH_GAIN = 1.1

/**
 * The layout to draw in a panel of this size: the asked direction whenever it fits at full
 * size (scale 1 or more). Only when it must shrink does the other one replace it, if that fits
 * clearly better (a wide LR chain on a narrow screen turns top to bottom) or the asked one
 * would scroll sideways; the scale never goes under ``MIN_SCALE``.
 */
export function pickLayout(
  nodes: DiagramNodeInput[],
  edges: DiagramEdgeInput[],
  direction: DiagramDirection,
  availWidth: number,
  availHeight: number,
): DiagramLayout & { scale: number } {
  const asked = layoutDiagram(nodes, edges, direction)
  const askedScale = fitScale(asked, availWidth, availHeight)
  // The asked direction that fits (drawn at full size or larger) is never replaced.
  if (askedScale >= 1) return { ...asked, scale: askedScale }
  const other = layoutDiagram(nodes, edges, OTHER[direction])
  const otherScale = fitScale(other, availWidth, availHeight)
  // Where the floor makes the panel scroll anyway, scroll down (the page's way) rather than sideways.
  const sideways = askedScale < MIN_SCALE && asked.width * MIN_SCALE > availWidth && other.width * MIN_SCALE <= availWidth
  const useOther = otherScale > askedScale * SWITCH_GAIN || sideways
  return { ...(useOther ? other : asked), scale: Math.max(MIN_SCALE, useOther ? otherScale : askedScale) }
}
