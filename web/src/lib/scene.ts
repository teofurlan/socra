import type { SceneObject, SceneState } from '@/types/scene'

/** A code object ready for a CodePane; ``focus`` is 1-based and inclusive. */
export interface CodeView {
  id: string
  code: string
  language: string
  focus: [number, number] | null
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
