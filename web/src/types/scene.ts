/** One thing a narrated scene can show; its primitive decides how it is drawn. */
export interface SceneObject {
  id: string
  primitive: string
  params: Record<string, unknown>
  /** Starts hidden until a step shows it. */
  hidden: boolean
}

/** An object's state while a step speaks: always its visibility, plus what its primitive tracks. */
export interface ObjectState {
  visible: boolean
  [key: string]: unknown
}

/** Every object's state while a step speaks, resolved by the server; keyed by object id. */
export type SceneState = Record<string, ObjectState>
