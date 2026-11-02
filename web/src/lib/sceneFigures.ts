/**
 * What the particles assemble while a narrated scene plays. Each source names its figure,
 * finds its box on screen every frame (so it follows panels that slide or scroll), and
 * builds its points once from the first box it is shown in.
 */
import { outlinePoints } from '@/lib/particleFigures'
import type { FigureBox, FigurePoint } from '@/lib/particleField'
import type { WalkthroughData } from '@/types/exam'

export interface FigureSource {
  /** Changes whenever what the figure shows changes, so its particles are recruited again. */
  id: string
  role: 'lead' | 'pointer'
  /** Where it is on screen now, or ``null`` while it cannot be seen. */
  box: () => FigureBox | null
  build: (box: FigureBox) => FigurePoint[]
}

/** Space around the focused lines, in pixels. */
const MARGIN = 6
/** A box squeezed thinner than this by scrolling is out of sight. */
const MIN_SIDE = 12
const OUTLINE_SPACING = 8
const MAX_OUTLINE_POINTS = 220

function isRange(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2 && value.every((n) => typeof n === 'number')
}

/**
 * The focused lines of a scene code object on screen, padded, and clipped to the part of
 * its scrolling code that is visible.
 */
function focusBox(objectId: string): FigureBox | null {
  const pre = document.querySelector<HTMLElement>(`pre[data-scene-object="${objectId}"]`)
  const lines = pre?.querySelectorAll<HTMLElement>('[data-focused="true"]')
  if (!pre || !lines?.length) return null
  const first = lines[0].getBoundingClientRect()
  const last = lines[lines.length - 1].getBoundingClientRect()
  const view = pre.getBoundingClientRect()
  const left = Math.min(first.left, last.left) - MARGIN
  const right = Math.max(first.right, last.right) + MARGIN
  const top = Math.max(first.top - MARGIN, view.top)
  const bottom = Math.min(last.bottom + MARGIN, view.bottom)
  if (bottom - top < MIN_SIDE || right - left < MIN_SIDE) return null
  return { x: left, y: top, w: right - left, h: bottom - top }
}

function outline(box: FigureBox): FigurePoint[] {
  const count = Math.min(MAX_OUTLINE_POINTS, Math.round((2 * (box.w + box.h)) / OUTLINE_SPACING))
  return outlinePoints(count, box.w, box.h)
}

/** The figures a scene shows right now; none once it has ended. */
export function sceneFigureSources(walkthrough: WalkthroughData | null): FigureSource[] {
  if (!walkthrough || walkthrough.status === 'ended' || !walkthrough.step) return []
  const state = walkthrough.step.state
  return walkthrough.objects.flatMap((object): FigureSource[] => {
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
}
