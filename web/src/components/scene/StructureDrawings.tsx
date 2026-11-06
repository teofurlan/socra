import type { CSSProperties, ReactNode } from 'react'
import { lastKey, pathKeys, touchedParts, type Item, type StructureView } from '@/lib/sceneStructure'
import { FONT, PAD, SMALL_FONT, slotRect, type HashLayout, type Rect, type RowLayout, type StackLayout, type TreeLayout } from '@/lib/structureLayout'

/** One hop of a lookup or a tree walk lights its element this long after the one before, in seconds. */
const PROBE_S = 0.35
const ENTER_RISE = 22

type Anim = 'enter' | 'slide' | 'flash' | 'pulse' | 'probe'

interface Motion {
  anim: Anim
  dx?: number
  dy?: number
  delay?: number
}

interface DrawProps<L> {
  view: StructureView
  layout: L
  /** Under reduced motion the final state is drawn at once: no animation, no element that is leaving. */
  reduced: boolean
}

function Part({ id, view, touched, motion, reduced, children }: {
  id: string
  view: StructureView
  touched: Set<string>
  motion?: Motion
  reduced: boolean
  children: ReactNode
}) {
  const isTouched = touched.has(id)
  const play = motion && !reduced
  const style: CSSProperties & Record<string, string> = {}
  if (play) {
    style['--dx'] = `${motion.dx ?? 0}px`
    style['--dy'] = `${motion.dy ?? 0}px`
    style['--delay'] = `${motion.delay ?? 0}s`
  }
  return (
    // The key changes with the operation for what it touched, so its animation plays again.
    <g
      key={isTouched || motion ? `${id}:${lastKey(view.last)}` : id}
      data-structure-part={id}
      data-touched={isTouched ? 'true' : undefined}
      data-anim={play ? motion.anim : undefined}
      className="structure-part"
      style={style}
    >
      {children}
    </g>
  )
}

function Box({ r, text, fontSize = FONT, rx = 6 }: { r: Rect; text: Item; fontSize?: number; rx?: number }) {
  return (
    <>
      <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={rx} />
      <text x={r.x + r.w / 2} y={r.y + r.h / 2} textAnchor="middle" dominantBaseline="central" fontSize={fontSize}>
        {String(text)}
      </text>
    </>
  )
}

function Leaving({ r, value }: { r: Rect; value: Item | undefined }) {
  if (value === undefined) return null
  return (
    <g data-structure-ghost="true" className="structure-part" data-anim="leave" aria-hidden="true">
      <Box r={r} text={value} />
    </g>
  )
}

function Empty({ r, label }: { r: Rect; label: string }) {
  return (
    <g data-structure-empty="true" className="structure-empty">
      <rect x={r.x} y={r.y} width={r.w} height={r.h} rx={6} />
      <text x={r.x + r.w / 2} y={r.y + r.h / 2} textAnchor="middle" dominantBaseline="central" fontSize={SMALL_FONT}>
        {label}
      </text>
    </g>
  )
}

const centre = (r: Rect) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 })

/** The cell of an array: its value, and its index beneath. */
export function ArrayDrawing({ view, layout, reduced }: DrawProps<RowLayout>) {
  const touched = new Set(touchedParts(view))
  const last = view.last
  const [a, b] = last?.indexes ?? []
  const motionOf = (i: number): Motion | undefined => {
    if (!last || !touched.has(`cell:${i}`)) return undefined
    if (last.op === 'swap') {
      const from = layout.cells[i === a ? b : a]
      const here = layout.cells[i]
      return { anim: 'slide', dx: from.x - here.x, dy: from.y - here.y }
    }
    if (last.op === 'set') return { anim: 'enter', dy: -12 }
    return { anim: last.op === 'compare' ? 'flash' : 'pulse' }
  }
  return layout.cells.map((cell) => (
    <Part key={cell.i} id={`cell:${cell.i}`} view={view} touched={touched} motion={motionOf(cell.i)} reduced={reduced}>
      <Box r={cell} text={view.items[cell.i]} />
      <text className="structure-index" x={cell.x + cell.w / 2} y={cell.y + cell.h + 14} textAnchor="middle" fontSize={SMALL_FONT}>
        {cell.i}
      </text>
    </Part>
  ))
}

/** A stack drawn upright: the top is the highest cell, and a pushed or popped cell moves through the spare row above it. */
export function StackDrawing({ view, layout, reduced }: DrawProps<StackLayout>) {
  const popped = view.last?.op === 'pop' ? view.last.value : undefined
  const touched = new Set(touchedParts(view))
  const rise = layout.ghost.h + 4
  const top = layout.cells[layout.cells.length - 1]
  const motionOf = (i: number): Motion | undefined => {
    if (!view.last || !touched.has(`cell:${i}`)) return undefined
    return view.last.op === 'push' ? { anim: 'enter', dy: -rise } : { anim: 'pulse' }
  }
  const empty = { x: PAD, y: layout.ghost.y, w: layout.cellW, h: layout.ghost.h }
  return (
      <>
        <line className="structure-base" x1={PAD - 4} x2={PAD + layout.cellW + 4} y1={layout.baseY} y2={layout.baseY} />
        {layout.cells.map((cell) => (
          <Part key={cell.i} id={`cell:${cell.i}`} view={view} touched={touched} motion={motionOf(cell.i)} reduced={reduced}>
            <Box r={cell} text={view.items[cell.i]} />
          </Part>
        ))}
        {layout.cells.length === 0 && <Empty r={{ ...empty, y: layout.baseY - empty.h - 4 }} label="empty" />}
        {top && (
          <text className="structure-index" x={top.x + top.w + 10} y={top.y + top.h / 2} dominantBaseline="central" fontSize={SMALL_FONT}>
            top
          </text>
        )}
        {!reduced && <Leaving r={layout.ghost} value={popped} />}
      </>
  )
}

/** A queue drawn as a row: the front is the first cell, the back the last. */
export function QueueDrawing({ view, layout, reduced }: DrawProps<RowLayout>) {
  const gone = view.last?.op === 'dequeue' ? view.last.value : undefined
  const touched = new Set(touchedParts(view))
  const motionOf = (i: number): Motion | undefined => {
    if (!view.last || !touched.has(`cell:${i}`)) return undefined
    return view.last.op === 'enqueue' ? { anim: 'enter', dx: ENTER_RISE } : { anim: 'pulse' }
  }
  const lastIndex = view.items.length - 1
  const label = (i: number) => (i === 0 && i === lastIndex ? 'front · back' : i === 0 ? 'front' : i === lastIndex ? 'back' : '')
  return (
      <>
        {layout.cells.map((cell) => (
          <Part key={cell.i} id={`cell:${cell.i}`} view={view} touched={touched} motion={motionOf(cell.i)} reduced={reduced}>
            <Box r={cell} text={view.items[cell.i]} />
            {label(cell.i) && (
              <text className="structure-index" x={cell.x + cell.w / 2} y={cell.y + cell.h + 14} textAnchor="middle" fontSize={SMALL_FONT}>
                {label(cell.i)}
              </text>
            )}
          </Part>
        ))}
        {view.items.length === 0 && <Empty r={slotRect(layout, 0)} label="empty" />}
        {!reduced && <Leaving r={slotRect(layout, 0)} value={gone} />}
      </>
  )
}

/** Buckets as rows; keys that landed in the same bucket are chained to its right, in insertion order. */
export function HashTableDrawing({ view, layout, reduced }: DrawProps<HashLayout>) {
  const last = view.last
  const removed = last?.op === 'remove' ? last.key : undefined
  const touched = new Set(touchedParts(view))
  const probes = last?.op === 'lookup' ? (last.probes ?? 0) : 0
  const motionOf = (b: number, p: number): Motion | undefined => {
    if (!last || last.bucket !== b) return undefined
    if (last.op === 'insert' && last.position === p) return { anim: 'enter', dy: -ENTER_RISE, delay: PROBE_S }
    if (last.op === 'lookup' && p < probes) return { anim: 'probe', delay: p * PROBE_S }
    return undefined
  }
  const ghostAt = (b: number) => {
    const row = layout.rows[b]
    const at = last?.position ?? 0
    return { x: PAD + layout.labelW + at * (layout.cellW + layout.arrow), y: row.y, w: layout.cellW, h: row.h }
  }
  return layout.rows.map((row) => {
      const active = last?.bucket === row.b
      return (
        <g
          key={row.b}
          data-structure-row={row.b}
          data-active={active ? 'true' : undefined}
          data-collision={active && last?.op === 'insert' && last.collision ? 'true' : undefined}
          className="structure-row"
        >
          <Part id={`bucket:${row.b}`} view={view} touched={touched} motion={touched.has(`bucket:${row.b}`) ? { anim: 'pulse' } : undefined} reduced={reduced}>
            <rect className="structure-bucket" x={PAD - 4} y={row.y - 2} width={layout.width - PAD * 2 + 8} height={row.h + 4} rx={8} />
            <text className="structure-index" x={PAD + 2} y={row.y + row.h / 2} dominantBaseline="central" fontSize={SMALL_FONT}>
              {row.b}
            </text>
          </Part>
          {row.entries.length === 0 && (
            <text className="structure-index" x={PAD + layout.labelW + 4} y={row.y + row.h / 2} dominantBaseline="central" fontSize={SMALL_FONT}>
              empty
            </text>
          )}
          {row.entries.map((entry) => (
            <g key={entry.p}>
              {entry.p > 0 && (
                <g className="structure-link" aria-hidden="true">
                  <line x1={entry.x - layout.arrow + 2} x2={entry.x - 3} y1={entry.y + entry.h / 2} y2={entry.y + entry.h / 2} />
                  <polygon points={`${entry.x - 1},${entry.y + entry.h / 2} ${entry.x - 7},${entry.y + entry.h / 2 - 4} ${entry.x - 7},${entry.y + entry.h / 2 + 4}`} />
                </g>
              )}
              <Part id={`entry:${row.b}:${entry.p}`} view={view} touched={touched} motion={motionOf(row.b, entry.p)} reduced={reduced}>
                <Box r={entry} text={view.buckets[row.b][entry.p]} />
              </Part>
            </g>
          ))}
          {!reduced && active && removed !== undefined && <Leaving r={ghostAt(row.b)} value={removed} />}
        </g>
      )
  })
}

/** Nodes where the server placed them (depth down, reading order across); the walk to the key lights node by node. */
export function TreeDrawing({ view, layout, reduced }: DrawProps<TreeLayout>) {
  const touched = new Set(touchedParts(view))
  const path = pathKeys(view)
  const last = view.last
  const motionOf = (key: number): Motion | undefined => {
    const hop = path.indexOf(key)
    if (!last || hop < 0) return undefined
    const arrives = last.op === 'insert' && hop === path.length - 1
    return arrives ? { anim: 'enter', dy: -ENTER_RISE, delay: hop * PROBE_S } : { anim: 'probe', delay: hop * PROBE_S }
  }
  return (
      <>
        {layout.edges.map((edge) => (
          <line key={`${edge.from}>${edge.to}`} data-structure-edge={`${edge.from}>${edge.to}`} className="structure-edge" x1={edge.x1} y1={edge.y1} x2={edge.x2} y2={edge.y2} />
        ))}
        {layout.nodes.map((node) => (
          <Part key={node.key} id={`node:${node.key}`} view={view} touched={touched} motion={motionOf(node.key)} reduced={reduced}>
            <g data-on-path={path.includes(node.key) ? 'true' : undefined}>
              <rect x={node.x} y={node.y} width={node.w} height={node.h} rx={node.h / 2} />
              <text x={centre(node).x} y={centre(node).y} textAnchor="middle" dominantBaseline="central" fontSize={FONT}>
                {node.key}
              </text>
            </g>
          </Part>
        ))}
        {layout.nodes.length === 0 && <Empty r={{ x: PAD, y: PAD, w: 70, h: 36 }} label="empty" />}
      </>
  )
}
