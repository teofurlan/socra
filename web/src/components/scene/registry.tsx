import type { ComponentType } from 'react'
import { CodeObject } from '@/components/scene/CodeObject'
import { DiagramObject } from '@/components/scene/DiagramObject'
import { visibleDiagramViews } from '@/lib/sceneDiagram'
import { visibleCodeViews } from '@/lib/scene'
import type { ObjectState, SceneObject, SceneState } from '@/types/scene'

/** What a primitive's component receives: its object, its state in the current step, and the step's text. */
export interface PrimitiveProps {
  object: SceneObject
  /** Null before the first step speaks. */
  state: ObjectState | null
  say: string
  /** How many objects of the scene share the panel, so names can tell them apart. */
  siblings: number
  /** The close button's name for this object's panel. */
  name: string
  onClose: () => void
}

/**
 * One primitive of the content panel. `visible` says whether it takes the panel right now;
 * `Component` draws it. A primitive that only the particles draw is not listed here.
 */
export interface PrimitiveRenderer {
  visible: (object: SceneObject, state: ObjectState | null) => boolean
  Component: ComponentType<PrimitiveProps>
}

export type PrimitiveRenderers = Record<string, PrimitiveRenderer>

const isShown = (object: SceneObject, state: ObjectState | null) => (state ? state.visible : !object.hidden)

/**
 * Primitives that draw in the content panel. Add one entry per primitive (code, a diagram, a data
 * structure) and it appears without touching the pages. `headline` and `shape` are drawn by
 * the particles alone (see sceneFigures.ts), so they take no panel.
 */
export const PRIMITIVE_RENDERERS: PrimitiveRenderers = {
  code: {
    visible: (object, state) => isShown(object, state) && visibleCodeViews([object], state ? { [object.id]: state } : null).length > 0,
    Component: CodeObject,
  },
  diagram: {
    visible: (object, state) => visibleDiagramViews([object], state ? { [object.id]: state } : null).length > 0,
    Component: DiagramObject,
  },
}

/** Drawn by the particles only: no panel, never a fallback. */
const PARTICLE_ONLY = new Set(['headline', 'shape'])

export interface PanelEntry {
  object: SceneObject
  current: ObjectState | null
  /** Null for an unknown primitive, drawn as the step's text. */
  renderer: PrimitiveRenderer | null
}

export function panelObjects(objects: SceneObject[], state: SceneState | null, renderers: PrimitiveRenderers): PanelEntry[] {
  return objects.flatMap((object): PanelEntry[] => {
    const current = state?.[object.id] ?? null
    const renderer = renderers[object.primitive]
    if (renderer) return renderer.visible(object, current) ? [{ object, current, renderer }] : []
    if (PARTICLE_ONLY.has(object.primitive)) return []
    // Unknown primitive: the step's text stands in for it while it is shown.
    return isShown(object, current) ? [{ object, current, renderer: null }] : []
  })
}

/** Whether the scene has anything to put in the content panel in its current step. */
export function hasScenePanel(objects: SceneObject[], state: SceneState | null, renderers: PrimitiveRenderers = PRIMITIVE_RENDERERS): boolean {
  return panelObjects(objects, state, renderers).length > 0
}
