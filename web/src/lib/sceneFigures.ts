/**
 * What the particles assemble while a narrated scene plays. Each source names its figure,
 * finds its box on screen every frame (so it follows panels that slide or scroll), and
 * builds its points once from the first box it is shown in.
 */
import { outlinePoints, textFigure } from '@/lib/particleFigures'
import type { FigureBox, FigurePoint } from '@/lib/particleField'
import type { WalkthroughData } from '@/types/exam'

export interface FigureSource {
  /** Changes whenever what the figure shows changes, so its particles are recruited again. */
  id: string
  role: 'lead' | 'pointer'
  /** Opt in to the 3D projection (see ``Figure.depth``); headlines and outlines stay flat. */
  depth?: boolean
  /** Where it is on screen now, or ``null`` while it cannot be seen. */
  box: () => FigureBox | null
  build: (box: FigureBox) => FigurePoint[]
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
  if (!walkthrough || walkthrough.status === 'ended' || !walkthrough.step) return null
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

/** The figures a scene shows right now (headline first); none once it has ended. */
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
  return headline ? [headlineSource(headline.id, headline.text), ...focus] : focus
}
