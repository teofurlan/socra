/**
 * What the agent points at in a finished scene, applied on top of its last step. The server has
 * already checked every target; this only draws it, reusing the emphasis the scene already has:
 * a diagram node is highlighted as a `highlight` cue does, code lines are focused, and a structure
 * part is marked like a touched one.
 */
import { visibleDiagramViews } from '@/lib/sceneDiagram'
import { allParts, visibleStructureViews } from '@/lib/sceneStructure'
import type { WalkthroughData } from '@/types/exam'
import type { ObjectState, PointTarget, SceneObject, SceneState } from '@/types/scene'

function lineCount(object: SceneObject): number {
  const code = object.params.code
  return typeof code === 'string' ? code.replace(/\n$/, '').split('\n').length : 1
}

function emphasize(object: SceneObject, current: ObjectState, targets: PointTarget[]): ObjectState {
  const whole = targets.some((t) => t.part === undefined && t.lines === undefined)
  const parts = targets.flatMap((t) => (t.part === undefined ? [] : [t.part]))
  switch (object.primitive) {
    case 'code': {
      const lines = targets.find((t) => t.lines)?.lines
      return lines ? { ...current, lines } : whole ? { ...current, lines: [1, lineCount(object)] } : current
    }
    case 'diagram': {
      const view = visibleDiagramViews([object], { [object.id]: current })[0]
      if (!view) return current
      const ids = new Set(view.nodes.map((n) => n.id))
      const nodes = whole ? [...ids] : parts.filter((p) => ids.has(p))
      if (nodes.length === 0) return current
      return { ...current, highlighted: nodes, dimmed: [...view.dimmed].filter((n) => !nodes.includes(n)) }
    }
    case 'structure': {
      const view = visibleStructureViews([object], { [object.id]: current })[0]
      if (!view) return current
      const known = new Set(allParts(view))
      const pointed = whole ? [...known] : parts.filter((p) => known.has(p))
      return pointed.length > 0 ? { ...current, pointed } : current
    }
    default:
      return current
  }
}

/** The state to draw: the step's own, with the pointed objects emphasized; null before the first step. */
export function pointedState(walkthrough: WalkthroughData): SceneState | null {
  const state = walkthrough.step?.state ?? null
  const targets = walkthrough.pointing
  if (!state || !targets || targets.length === 0) return state
  const next: SceneState = { ...state }
  for (const object of walkthrough.objects) {
    const current = state[object.id]
    const mine = targets.filter((t) => t.object === object.id)
    if (current?.visible && mine.length > 0) next[object.id] = emphasize(object, current, mine)
  }
  return next
}
