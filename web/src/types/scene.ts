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

/** What the agent points at in a finished scene; the server has already checked it against the scene. */
export interface PointTarget {
  object: string
  /** A diagram node id, or a structure part (`cell:<i>`, `bucket:<b>`, `entry:<b>:<p>`, `node:<key>`). */
  part?: string
  /** Code only: a 1-based inclusive line range. */
  lines?: [number, number]
}

/** Every object's state while a step speaks, resolved by the server; keyed by object id. */
export type SceneState = Record<string, ObjectState>
