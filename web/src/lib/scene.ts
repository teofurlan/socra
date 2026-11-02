import type { SceneObject, SceneState } from '@/types/scene'

/** A code object ready for a CodePane; ``focus`` is 1-based and inclusive. */
export interface CodeView {
  id: string
  code: string
  language: string
  focus: [number, number] | null
}

/** A 3D shape object ready for a ShapePane. */
export interface ShapeView {
  id: string
  shape: 'cube' | 'cylinder' | 'cone' | 'sphere' | 'torus'
  color: string
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
 * The 3D shape objects to draw right now.
 */
export function visibleShapeViews(objects: SceneObject[], state: SceneState | null): ShapeView[] {
  return objects.flatMap((object) => {
    if (object.primitive !== 'shape') return []
    const shape = object.params.shape
    if (typeof shape !== 'string') return []
    const current = state?.[object.id]
    if (!(current ? current.visible : !object.hidden)) return []
    const activeShape = (typeof current?.shape === 'string' ? current.shape : shape) as ShapeView['shape']
    const color = typeof current?.color === 'string' ? current.color : (typeof object.params.color === 'string' ? object.params.color : '')
    const wireframe = typeof current?.wireframe === 'boolean' ? current.wireframe : Boolean(object.params.wireframe)
    const rx = typeof current?.rx === 'number' ? current.rx : 0
    const ry = typeof current?.ry === 'number' ? current.ry : 0
    const rz = typeof current?.rz === 'number' ? current.rz : 0
    return [{
      id: object.id,
      shape: activeShape,
      color,
      wireframe,
      rx,
      ry,
      rz,
    }]
  })
}
