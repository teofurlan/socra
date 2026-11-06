import { SOLID_KINDS, type SolidKind } from '@/lib/solidShapes'
import type { SceneObject, SceneState } from '@/types/scene'

/** A code object ready for a CodePane; ``focus`` is 1-based and inclusive. */
export interface CodeView {
  id: string
  code: string
  language: string
  focus: [number, number] | null
}

/** A 3D shape object ready for the particles to assemble; ``rx, ry, rz`` are its rotation in turns. */
export interface ShapeView {
  id: string
  shape: SolidKind
  wireframe: boolean
  rx: number
  ry: number
  rz: number
}

/** Identifies a scene's code for the close button: another scene, or other code, opens the pane again. */
export function sceneKey(title: string, objects: SceneObject[]): string {
  return `scene:${title}:${JSON.stringify(objects)}`
}

function isRange(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2 && value.every((n) => typeof n === 'number')
}

/**
 * The code objects to draw right now. Before the first step speaks there is no state yet,
 * so every object that does not start hidden is shown, unfocused.
 */
export function visibleCodeViews(objects: SceneObject[], state: SceneState | null): CodeView[] {
  return objects.flatMap((object) => {
    const { code, language } = object.params
    if (object.primitive !== 'code' || typeof code !== 'string') return []
    const current = state?.[object.id]
    if (!(current ? current.visible : !object.hidden)) return []
    return [{
      id: object.id,
      code,
      language: typeof language === 'string' ? language : '',
      focus: isRange(current?.lines) ? current.lines : null,
    }]
  })
}

/**
 * The 3D shape objects to draw right now: the same rule as code (before the first step, those
 * that do not start hidden), with the kind, wireframe and rotation of the current step.
 */
export function visibleShapeViews(objects: SceneObject[], state: SceneState | null): ShapeView[] {
  return objects.flatMap((object) => {
    if (object.primitive !== 'shape') return []
    const current = state?.[object.id]
    if (!(current ? current.visible : !object.hidden)) return []
    const kind = typeof current?.shape === 'string' ? current.shape : object.params.shape
    const activeShape = SOLID_KINDS.find((k) => k === kind)
    if (!activeShape) return []
    const wireframe = typeof current?.wireframe === 'boolean' ? current.wireframe : Boolean(object.params.wireframe)
    const rx = typeof current?.rx === 'number' ? current.rx : 0
    const ry = typeof current?.ry === 'number' ? current.ry : 0
    const rz = typeof current?.rz === 'number' ? current.rz : 0
    return [{
      id: object.id,
      shape: activeShape,
      wireframe,
      rx,
      ry,
      rz,
    }]
  })
}
