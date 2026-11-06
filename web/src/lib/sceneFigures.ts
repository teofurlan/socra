/**
 * What the particles assemble while a narrated scene plays. Each source names its figure,
 * finds its box on screen every frame (so it follows panels that slide or scroll), and
 * builds its points once from the first box it is shown in.
 */
import { outlinePoints, solidFigurePoints, textFigure } from '@/lib/particleFigures'
import { visibleShapeViews, type ShapeView } from '@/lib/scene'
import { visibleDiagramViews } from '@/lib/sceneDiagram'
import { lastKey, touchedParts, visibleStructureViews } from '@/lib/sceneStructure'
import type { SolidPose } from '@/lib/solidShapes'
import type { FigureBox, FigurePoint } from '@/lib/particleField'
import type { WalkthroughData } from '@/types/exam'

export interface FigureSource {
  /** Changes whenever what the figure shows changes, so its particles are recruited again. */
  id: string
  role: 'lead' | 'pointer'
  /** Opt in to the 3D projection (see ``Figure.depth``); headlines and outlines stay flat. */
  depth?: boolean
  /** A solid's rotation from the scene state, in turns (with ``depth``); see ``Figure.pose``. */
  pose?: SolidPose
  /** Where it is on screen now, or ``null`` while it cannot be seen. */
  box: () => FigureBox | null
  build: (box: FigureBox) => FigurePoint[]
  /**
   * Read every frame with the box: when it changes, the points are built again (same id, so the
   * particles stay recruited). For figures whose points depend on what is on screen, not only on the id.
   */
  rebuildKey?: (box: FigureBox) => string
}

/** Space above and below the focused lines, in pixels; lines sit close, so it stays small. */
const MARGIN = 3
/** A box squeezed thinner than this by scrolling is out of sight. */
const MIN_SIDE = 12
const OUTLINE_SPACING = 8
const MAX_OUTLINE_POINTS = 220

function isRange(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2 && value.every((n) => typeof n === 'number')
}

/**
 * The focused lines of a scene code object on screen, padded, and clipped to the part of
 * its scrolling code that is visible: lines are as wide as the longest one, often wider
 * than the pane, so the box never leaves the pane sideways either.
 */
function focusBox(objectId: string): FigureBox | null {
  const pre = document.querySelector<HTMLElement>(`pre[data-scene-object="${objectId}"]`)
  const lines = pre?.querySelectorAll<HTMLElement>('[data-focused="true"]')
  if (!pre || !lines?.length) return null
  const first = lines[0].getBoundingClientRect()
  const last = lines[lines.length - 1].getBoundingClientRect()
  const view = pre.getBoundingClientRect()
  const left = Math.max(Math.min(first.left, last.left), view.left)
  const right = Math.min(Math.max(first.right, last.right), view.right)
  const top = Math.max(first.top - MARGIN, view.top)
  const bottom = Math.min(last.bottom + MARGIN, view.bottom)
  if (bottom - top < MIN_SIDE || right - left < MIN_SIDE) return null
  return { x: left, y: top, w: right - left, h: bottom - top }
}

function outline(box: FigureBox): FigurePoint[] {
  const count = Math.min(MAX_OUTLINE_POINTS, Math.round((2 * (box.w + box.h)) / OUTLINE_SPACING))
  return outlinePoints(count, box.w, box.h)
}

/** Same family as the page text (--sans in index.css), so the headline matches the UI. */
const HEADLINE_FONT = '"Geist Variable", "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif'
/**
 * The most points a headline asks for: the largest figure budget a screen offers (0.7 of the
 * 1800-particle ceiling, reached at 1920x1080 and up). Smaller screens recruit fewer, spread
 * evenly over the points, and ParticleField enlarges the dots there (headlineDotScale).
 */
const HEADLINE_POINTS = 1260
/** How much of the voice stage the headline may fill. */
const HEADLINE_WIDTH = 0.9
const HEADLINE_HEIGHT = 0.7

function liveState(walkthrough: WalkthroughData | null) {
  if (!walkthrough || !walkthrough.step) return null
  // A scene that played to its end leaves its last step up until the user speaks; a stopped or
  // failed one clears at once.
  if (walkthrough.status === 'ended' && walkthrough.reason !== 'completed') return null
  return walkthrough.step.state
}

/** The first visible headline of the current step, if any; the page draws only this one. */
export function sceneHeadline(walkthrough: WalkthroughData | null): { id: string; text: string } | null {
  const state = liveState(walkthrough)
  if (!state || !walkthrough) return null
  for (const object of walkthrough.objects) {
    const current = state[object.id]
    if (object.primitive === 'headline' && current?.visible && typeof current.text === 'string' && current.text) {
      return { id: object.id, text: current.text }
    }
  }
  return null
}

/** The text, as wide as the stage allows without distorting it, centred on the stage. */
function headlineSource(id: string, text: string): FigureSource {
  let figure: ReturnType<typeof textFigure> | undefined
  const rasterized = () => (figure === undefined ? (figure = textFigure(text, HEADLINE_POINTS, HEADLINE_FONT)) : figure)
  return {
    id: `headline:${id}:${text}`,
    role: 'lead',
    box: () => {
      const stage = document.querySelector<HTMLElement>('.voice-stage')?.getBoundingClientRect()
      const raster = rasterized()
      if (!stage || !raster || raster.aspect <= 0) return null
      const w = Math.min(stage.width * HEADLINE_WIDTH, stage.height * HEADLINE_HEIGHT * raster.aspect)
      const h = w / raster.aspect
      if (w < MIN_SIDE || h < MIN_SIDE) return null
      return { x: stage.left + (stage.width - w) / 2, y: stage.top + (stage.height - h) / 2, w, h }
    },
    build: () => rasterized()?.points ?? [],
  }
}

/**
 * How many points a shape asks for: the same ceiling as a headline (the largest figure budget a
 * screen offers). Smaller screens recruit fewer and spread evenly over the points, which are
 * ordered so that a stride through them still covers the whole solid.
 */
const SHAPE_POINTS = 1260
/**
 * How much of the shorter side of the voice stage a shape's box takes. The box holds the solid
 * in any pose; perspective magnifies the near side by up to about 1.5x, so the box stays well
 * inside the stage and the near side does not leave it.
 */
const SHAPE_SIZE = 0.7

/** The first visible shape of the current step, if any; it takes the stage over a headline. */
function sceneShape(walkthrough: WalkthroughData | null): ShapeView | null {
  const state = liveState(walkthrough)
  if (!state || !walkthrough) return null
  return visibleShapeViews(walkthrough.objects, state)[0] ?? null
}

/**
 * The solid as 3D points in a square box centred on the stage. Its id names the kind and
 * wireframe but not the pose, so turning it keeps its particles and changing the solid recruits
 * them again; the pose travels beside the points and is read every frame.
 */
function shapeSource(view: ShapeView): FigureSource {
  return {
    id: `shape:${view.id}:${view.shape}:${view.wireframe ? 'wire' : 'solid'}`,
    role: 'lead',
    depth: true,
    pose: { rx: view.rx, ry: view.ry, rz: view.rz },
    box: () => {
      const stage = document.querySelector<HTMLElement>('.voice-stage')?.getBoundingClientRect()
      if (!stage) return null
      const side = Math.min(stage.width, stage.height) * SHAPE_SIZE
      if (side < MIN_SIDE) return null
      return { x: stage.left + (stage.width - side) / 2, y: stage.top + (stage.height - side) / 2, w: side, h: side }
    },
    build: () => solidFigurePoints(view.shape, view.wireframe, SHAPE_POINTS),
  }
}

/** How many highlighted nodes the particles outline at once; the rest stay highlighted in the SVG only. */
const MAX_NODE_OUTLINES = 4
const PATH_SPACING = 8
const MAX_PATH_POINTS = 220
const MIN_PATH_POINTS = 8

function diagramRoot(objectId: string): Element | null {
  return document.querySelector(`[data-diagram-root][data-scene-object="${objectId}"]`)
}

/** What of a diagram is on screen: its scrolling viewport, since nodes can sit beyond its edge. */
function diagramView(root: Element): DOMRect {
  return (root.closest('[data-diagram-viewport]') ?? root).getBoundingClientRect()
}

function clip(left: number, top: number, right: number, bottom: number, view: DOMRect): FigureBox | null {
  const x = Math.max(left, view.left)
  const y = Math.max(top, view.top)
  const w = Math.min(right, view.right) - x
  const h = Math.min(bottom, view.bottom) - y
  return w < MIN_SIDE || h < MIN_SIDE ? null : { x, y, w, h }
}

/** A highlighted node's box on screen, padded like the focused code lines. */
function nodeBox(objectId: string, nodeId: string): FigureBox | null {
  const root = diagramRoot(objectId)
  const rect = root?.querySelector(`[data-diagram-node="${nodeId}"] rect`)?.getBoundingClientRect()
  if (!root || !rect) return null
  return clip(rect.left - MARGIN, rect.top - MARGIN, rect.right + MARGIN, rect.bottom + MARGIN, diagramView(root))
}

function tracedLines(objectId: string, path: string[]): SVGGeometryElement[] {
  const root = diagramRoot(objectId)
  if (!root) return []
  return path.slice(1).flatMap((id, i) => {
    const line = root.querySelector<SVGGeometryElement>(`[data-diagram-edge="${path[i]}>${id}"] path`)
    return line ? [line] : []
  })
}

/** The traced edges on screen as one box (padded, so a straight edge still has an area). */
function traceBox(objectId: string, path: string[]): FigureBox | null {
  const root = diagramRoot(objectId)
  const rects = tracedLines(objectId, path).map((line) => line.getBoundingClientRect())
  if (!root || rects.length === 0) return null
  const pad = MARGIN + 1
  let left = Math.min(...rects.map((r) => r.left)) - pad
  let top = Math.min(...rects.map((r) => r.top)) - pad
  let right = Math.max(...rects.map((r) => r.right)) + pad
  let bottom = Math.max(...rects.map((r) => r.bottom)) + pad
  // A straight horizontal or vertical edge has no thickness: give the box room so it is not read as out of sight.
  const room = MIN_SIDE * 2
  if (right - left < room) { const mid = (left + right) / 2; left = mid - room / 2; right = mid + room / 2 }
  if (bottom - top < room) { const mid = (top + bottom) / 2; top = mid - room / 2; bottom = mid + room / 2 }
  return clip(left, top, right, bottom, diagramView(root))
}

/** Points along each traced edge, from the first to the last, as screen pixels. */
function tracePixels(lines: SVGGeometryElement[]): { x: number; y: number }[] {
  const lengths = lines.map((line) => (typeof line.getTotalLength === 'function' ? line.getTotalLength() : 0))
  const scale = lines.map((line) => line.getScreenCTM?.()?.a ?? 1)
  const pixels = lengths.map((length, i) => length * scale[i])
  const total = pixels.reduce((a, b) => a + b, 0)
  const count = Math.max(MIN_PATH_POINTS, Math.min(MAX_PATH_POINTS, Math.round(total / PATH_SPACING)))
  const out: { x: number; y: number }[] = []
  lines.forEach((line, i) => {
    const share = total > 0 ? pixels[i] / total : 1 / lines.length
    const here = Math.max(2, Math.round(count * share))
    const rect = line.getBoundingClientRect()
    for (let k = 0; k < here; k++) {
      const t = (k + 0.5) / here
      if (lengths[i] > 0 && typeof line.getPointAtLength === 'function' && line.getScreenCTM?.()) {
        const p = line.getPointAtLength(t * lengths[i])
        const m = line.getScreenCTM()!
        out.push({ x: m.a * p.x + m.c * p.y + m.e, y: m.b * p.x + m.d * p.y + m.f })
      } else {
        out.push({ x: rect.left + rect.width * t, y: rect.top + rect.height * t })
      }
    }
  })
  return out
}

/**
 * The particles point at a diagram the way they outline focused code: a ring around each
 * highlighted node, and a line along the edges of a traced path. Both are flat pointers.
 */
function diagramSources(walkthrough: WalkthroughData, state: NonNullable<ReturnType<typeof liveState>>): FigureSource[] {
  return visibleDiagramViews(walkthrough.objects, state).flatMap((view): FigureSource[] => {
    const rings = [...view.highlighted].slice(0, MAX_NODE_OUTLINES).map((nodeId): FigureSource => ({
      id: `highlight:${view.id}:${nodeId}`,
      role: 'pointer',
      box: () => nodeBox(view.id, nodeId),
      build: outline,
    }))
    const lines: FigureSource[] = view.trace.length < 2 ? [] : [{
      id: `trace:${view.id}:${view.trace.join('>')}`,
      role: 'pointer',
      box: () => traceBox(view.id, view.trace),
      // Points sit where the edges are on screen now: a new size (resize, zoom) or clip (scroll) rebuilds them.
      rebuildKey: (box) => {
        const scale = tracedLines(view.id, view.trace)[0]?.getScreenCTM?.()?.a ?? 1
        return `${Math.round(box.w / 4)}x${Math.round(box.h / 4)}@${scale.toFixed(2)}`
      },
      build: (box) =>
        tracePixels(tracedLines(view.id, view.trace)).flatMap((p) => {
          const x = (p.x - box.x) / box.w
          const y = (p.y - box.y) / box.h
          // Outside the clipped viewport the edge is out of sight: leave those points out.
          return x < 0 || x > 1 || y < 0 || y > 1 ? [] : [{ x, y }]
        }),
    }]
    return [...rings, ...lines]
  })
}

function structureRoot(objectId: string): Element | null {
  return document.querySelector(`[data-structure-root][data-scene-object="${objectId}"]`)
}

/** A part of a structure (a cell, a chain entry, a tree node, a bucket row) on screen, padded and clipped to its viewport. */
export function partBox(objectId: string, part: string): FigureBox | null {
  const root = structureRoot(objectId)
  // Compared as text, not put in a selector: an id with quotes or brackets must neither throw nor match another part.
  const found = [...(root?.querySelectorAll('[data-structure-part]') ?? [])].find((el) => el.getAttribute('data-structure-part') === part)
  const rect = found?.querySelector('rect')?.getBoundingClientRect()
  if (!root || !rect) return null
  const view = (root.closest('[data-structure-viewport]') ?? root).getBoundingClientRect()
  return clip(rect.left - MARGIN, rect.top - MARGIN, rect.right + MARGIN, rect.bottom + MARGIN, view)
}

/**
 * The particles outline what the latest operation touched in a structure, as they outline focused
 * code lines: the cell set, the two cells swapped, the chain entry found, the nodes of a search path.
 * Flat pointers; a removed element is gone from the drawing and is not outlined.
 */
function structureSources(walkthrough: WalkthroughData, state: NonNullable<ReturnType<typeof liveState>>): FigureSource[] {
  return visibleStructureViews(walkthrough.objects, state).flatMap((view) =>
    touchedParts(view).map((part): FigureSource => ({
      id: `touch:${view.id}:${lastKey(view.last)}:${part}`,
      role: 'pointer',
      box: () => partBox(view.id, part),
      // The outline is as big as the part is on screen now: a resize or a zoom builds it again.
      rebuildKey: (box) => `${Math.round(box.w / 4)}x${Math.round(box.h / 4)}`,
      build: outline,
    })),
  )
}

/**
 * The figures a scene shows right now (the lead first); none once it was stopped or failed (a completed scene holds its last step). A shape and a
 * headline both lead the stage: the shape wins and the headline is not drawn while it is visible.
 */
export function sceneFigureSources(walkthrough: WalkthroughData | null): FigureSource[] {
  const state = liveState(walkthrough)
  if (!state || !walkthrough) return []
  const headline = sceneHeadline(walkthrough)
  const focus = walkthrough.objects.flatMap((object): FigureSource[] => {
    const current = state[object.id]
    if (object.primitive !== 'code' || !current?.visible || !isRange(current.lines)) return []
    const [start, end] = current.lines
    return [{
      id: `focus:${object.id}:${start}-${end}`,
      role: 'pointer',
      box: () => focusBox(object.id),
      build: outline,
    }]
  })
  const pointers = [...focus, ...diagramSources(walkthrough, state), ...structureSources(walkthrough, state)]
  const shape = sceneShape(walkthrough)
  if (shape) return [shapeSource(shape), ...pointers]
  return headline ? [headlineSource(headline.id, headline.text), ...pointers] : pointers
}
