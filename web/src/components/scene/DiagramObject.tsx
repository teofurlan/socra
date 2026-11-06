import { useMemo, useRef, type CSSProperties } from 'react'
import { X } from 'lucide-react'
import { Panel } from '@/components/shell/Panel'
import type { PrimitiveProps } from '@/components/scene/registry'
import { EDGE_FONT, NODE_FONT, pickLayout, polylineLength, type PlacedEdge, type PlacedNode, type Point } from '@/lib/diagramLayout'
import { visibleDiagramViews, type DiagramView } from '@/lib/sceneDiagram'
import { useElementSize } from '@/lib/useElementSize'
import { usePrefersReducedMotion } from '@/lib/useReducedMotion'

/** Room around the drawing inside its scrolling viewport, in pixels. */
const VIEWPORT_PAD = 8
/** Used before the viewport is measured, and where ResizeObserver does not exist. */
const FALLBACK_SIZE = { width: 640, height: 420 }
/** A trace takes at most this long in all; one edge never takes longer than EDGE_MS. */
const TRACE_TOTAL_MS = 2400
const EDGE_MS = 450
const ARROW_LENGTH = 9
const ARROW_HALF = 5
const NOTE_LINE = 16
const NOTE_WRAP = 28

/** Colours a group can take, in the order groups first appear; ungrouped nodes stay neutral. */
const GROUP_COLORS = ['var(--accent)', 'var(--violet)', 'var(--live)', 'var(--orange)']

function arrowHead(points: Point[]): string {
  const tip = points[points.length - 1]
  let from = points[points.length - 2] ?? tip
  for (let i = points.length - 2; i >= 0; i--) {
    from = points[i]
    if (Math.hypot(tip.x - from.x, tip.y - from.y) >= ARROW_LENGTH) break
  }
  const length = Math.hypot(tip.x - from.x, tip.y - from.y) || 1
  const ux = (tip.x - from.x) / length
  const uy = (tip.y - from.y) / length
  const bx = tip.x - ux * ARROW_LENGTH
  const by = tip.y - uy * ARROW_LENGTH
  return `${tip.x},${tip.y} ${bx - uy * ARROW_HALF},${by + ux * ARROW_HALF} ${bx + uy * ARROW_HALF},${by - ux * ARROW_HALF}`
}

function noteLines(text: string): string[] {
  if (text.length <= NOTE_WRAP) return [text]
  const cut = text.lastIndexOf(' ', NOTE_WRAP)
  const at = cut > 8 ? cut : NOTE_WRAP
  return [text.slice(0, at).trim(), text.slice(at).trim()]
}

interface TraceTiming {
  edgeDelay: Map<string, number>
  nodeDelay: Map<string, number>
  duration: number
}

/** When each traced edge starts drawing and when its node lights, in seconds, in path order. */
function traceTiming(trace: string[], reduced: boolean): TraceTiming {
  const edgeDelay = new Map<string, number>()
  const nodeDelay = new Map<string, number>()
  const hops = Math.max(1, trace.length - 1)
  const each = reduced ? 0 : Math.min(EDGE_MS, TRACE_TOTAL_MS / hops) / 1000
  trace.forEach((id, index) => {
    if (!nodeDelay.has(id)) nodeDelay.set(id, index * each)
    if (index < trace.length - 1) {
      const key = `${id}>${trace[index + 1]}`
      if (!edgeDelay.has(key)) edgeDelay.set(key, index * each)
    }
  })
  return { edgeDelay, nodeDelay, duration: each }
}

function NodeBox({ node, view, tint, delay }: { node: PlacedNode; view: DiagramView; tint: string | null; delay: number | undefined }) {
  const lit = view.highlighted.has(node.id)
  const dimmed = view.dimmed.has(node.id) && !lit
  const onPath = delay !== undefined
  const style: CSSProperties & Record<string, string> = {}
  if (tint) style['--tint'] = tint
  if (onPath) style['--trace-delay'] = `${delay}s`
  return (
    <g
      data-diagram-node={node.id}
      data-highlighted={lit ? 'true' : undefined}
      data-dimmed={dimmed ? 'true' : undefined}
      data-traced={onPath ? 'true' : undefined}
      data-grouped={tint ? 'true' : undefined}
      className="diagram-node"
      style={style}
    >
      <rect x={node.x} y={node.y} width={node.width} height={node.height} rx={8} />
      {node.lines.map((line, i) => (
        <text
          key={i}
          x={node.x + node.width / 2}
          y={node.y + node.height / 2 + (i - (node.lines.length - 1) / 2) * 18}
          textAnchor="middle"
          dominantBaseline="central"
          fontSize={NODE_FONT}
        >
          {line}
        </text>
      ))}
    </g>
  )
}

function EdgeLine({ edge, view, timing, traced }: { edge: PlacedEdge; view: DiagramView; timing: TraceTiming; traced: boolean }) {
  const revealed = view.revealed.has(edge.key)
  const dimmed = (view.dimmed.has(edge.from) && !view.highlighted.has(edge.from)) || (view.dimmed.has(edge.to) && !view.highlighted.has(edge.to))
  const length = polylineLength(edge.points)
  const delay = timing.edgeDelay.get(edge.key)
  const style: CSSProperties & Record<string, string> = {}
  if (traced && delay !== undefined) {
    style['--len'] = `${Math.ceil(length)}`
    style['--trace-delay'] = `${delay}s`
    style['--trace-duration'] = `${timing.duration}s`
  }
  const d = edge.points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ')
  return (
    <g
      data-diagram-edge={edge.key}
      data-revealed={revealed ? 'true' : 'false'}
      data-traced={traced ? 'true' : undefined}
      data-dimmed={dimmed ? 'true' : undefined}
      className="diagram-edge"
      style={style}
    >
      <path d={d} className="diagram-edge-line" fill="none" />
      <polygon points={arrowHead(edge.points)} className="diagram-edge-arrow" />
      {edge.labelAt && (
        <g className="diagram-edge-label">
          <rect x={edge.labelAt.x - edge.labelWidth / 2} y={edge.labelAt.y - 9} width={edge.labelWidth} height={18} rx={4} />
          <text x={edge.labelAt.x} y={edge.labelAt.y} textAnchor="middle" dominantBaseline="central" fontSize={EDGE_FONT}>
            {edge.label}
          </text>
        </g>
      )}
    </g>
  )
}

function Note({ node, text, width }: { node: PlacedNode; text: string; width: number }) {
  const lines = noteLines(text)
  const boxWidth = Math.ceil(Math.max(...lines.map((l) => l.length)) * 6.9 + 16)
  const boxHeight = lines.length * NOTE_LINE + 8
  const x = Math.min(Math.max(node.x + node.width / 2 - boxWidth / 2, 2), Math.max(2, width - boxWidth - 2))
  const y = node.y + node.height + 6
  return (
    <g data-diagram-note={node.id} className="diagram-note">
      <rect x={x} y={y} width={boxWidth} height={boxHeight} rx={6} />
      {lines.map((line, i) => (
        <text key={i} x={x + boxWidth / 2} y={y + 4 + NOTE_LINE * (i + 0.5)} textAnchor="middle" dominantBaseline="central" fontSize={EDGE_FONT}>
          {line}
        </text>
      ))}
    </g>
  )
}

/** The diagram primitive: boxes, labels and arrows as SVG laid out by dagre, fitted to the panel. */
export function DiagramObject({ object, state, siblings, onClose }: PrimitiveProps) {
  const view = visibleDiagramViews([object], state ? { [object.id]: state } : null)[0]
  const viewport = useRef<HTMLDivElement | null>(null)
  const size = useElementSize(viewport, FALLBACK_SIZE)
  const reduced = usePrefersReducedMotion()
  // The layout depends on the diagram and the room it has, not on the step's highlights.
  const picked = useMemo(() => {
    const whole = visibleDiagramViews([{ ...object, hidden: false }], null)[0]
    return whole ? pickLayout(whole.nodes, whole.edges, whole.direction, size.width - VIEWPORT_PAD * 2, size.height - VIEWPORT_PAD * 2) : null
  }, [object, size.width, size.height])
  if (!view || !picked) return null

  const timing = traceTiming(view.trace, reduced)
  // A new trace remounts what it draws, so its animation plays again.
  const traceKey = view.trace.join('>')
  const tracedEdges = new Set(view.trace.slice(1).map((id, i) => `${view.trace[i]}>${id}`))
  const groups = [...new Set(view.nodes.map((n) => n.group).filter(Boolean))]
  const tintOf = (group: string) => (group ? GROUP_COLORS[groups.indexOf(group) % GROUP_COLORS.length] : null)
  const width = Math.round(picked.width * picked.scale)
  const height = Math.round(picked.height * picked.scale)
  const summary = `Diagram: ${view.nodes.map((n) => n.label).join(', ')}. ${view.edges
    .map((e) => `${view.nodes.find((n) => n.id === e.from)?.label} to ${view.nodes.find((n) => n.id === e.to)?.label}`)
    .join('; ')}`
  const nodeAt = new Map(picked.nodes.map((n) => [n.id, n]))

  return (
    <Panel
      label={siblings > 1 ? `Walkthrough diagram ${view.id}` : 'Walkthrough diagram'}
      testId="diagram-pane"
      className="h-full"
      title={<span>Diagram</span>}
      meta={
        <>
          <span className="t-mono truncate" style={{ color: 'var(--label-3)' }}>
            {view.nodes.length} {view.nodes.length === 1 ? 'node' : 'nodes'}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close diagram"
            title="Close the diagram panel"
            className="-mr-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md hover:bg-[var(--raise)] hover:text-[var(--label)]"
            style={{ color: 'var(--label-2)' }}
          >
            <X aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
          </button>
        </>
      }
    >
      <div ref={viewport} data-diagram-viewport className="diagram-viewport">
        <svg
          role="img"
          aria-label={summary}
          data-diagram-root
          data-scene-object={view.id}
          data-direction={picked.direction}
          data-scale={picked.scale.toFixed(3)}
          data-motion={reduced ? 'reduced' : 'full'}
          width={width}
          height={height}
          viewBox={`0 0 ${picked.width} ${picked.height}`}
          className="diagram-svg"
        >
          {picked.edges.map((edge) => (
            <EdgeLine key={`${edge.key}:${tracedEdges.has(edge.key) ? traceKey : ''}`} edge={edge} view={view} timing={timing} traced={tracedEdges.has(edge.key)} />
          ))}
          {picked.nodes.map((node) => (
            <NodeBox key={`${node.id}:${timing.nodeDelay.has(node.id) ? traceKey : ''}`} node={node} view={view} tint={tintOf(node.group)} delay={timing.nodeDelay.get(node.id)} />
          ))}
          {Object.entries(view.notes).map(([id, text]) => {
            const node = nodeAt.get(id)
            return node ? <Note key={id} node={node} text={text} width={picked.width} /> : null
          })}
        </svg>
      </div>
    </Panel>
  )
}
