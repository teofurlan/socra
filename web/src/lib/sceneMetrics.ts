/**
 * Timing of a narrated scene on the page, for checking sync: the time from the scene's
 * arrival (`present`) to its first visual, and, per step, the drift between its audio
 * starting and its cue being on screen. Kept in memory and readable at
 * `window.__socraSceneMetrics.snapshot()`; each reading is also a debug log line.
 */
export interface CueDrift {
  step: number
  ms: number
}

export interface SceneMetricsSnapshot {
  firstVisualMs: number | null
  drifts: CueDrift[]
}

export interface SceneMetrics {
  /** A scene arrived; starts the measurement over. */
  present: (now?: number) => void
  /** The scene's content was drawn; only the first one after `present` counts. */
  firstVisual: (now?: number) => void
  /** A step's audio began playing. */
  audioStart: (step: number, now?: number) => void
  /** A step's cue is on screen; counts against its audio start, once. */
  cueApplied: (step: number, now?: number) => void
  snapshot: () => SceneMetricsSnapshot
}

const clock = () => performance.now()

export function createSceneMetrics(log: (line: string) => void = () => {}): SceneMetrics {
  let presentAt: number | null = null
  let firstVisualMs: number | null = null
  let drifts: CueDrift[] = []
  const pending = new Map<number, number>()

  return {
    present(now = clock()) {
      presentAt = now
      firstVisualMs = null
      drifts = []
      pending.clear()
    },
    firstVisual(now = clock()) {
      if (presentAt === null || firstVisualMs !== null) return
      firstVisualMs = now - presentAt
      log(`scene first visual ${firstVisualMs.toFixed(0)} ms after present`)
    },
    audioStart(step, now = clock()) {
      pending.set(step, now)
    },
    cueApplied(step, now = clock()) {
      const started = pending.get(step)
      if (started === undefined) return
      pending.delete(step)
      drifts.push({ step, ms: now - started })
      log(`scene step ${step} cue drift ${(now - started).toFixed(0)} ms`)
    },
    snapshot: () => ({ firstVisualMs, drifts: drifts.map((d) => ({ ...d })) }),
  }
}

/** The page's own store. */
export const sceneMetrics = createSceneMetrics((line) => console.debug(`[socra] ${line}`))

if (typeof window !== 'undefined') {
  ;(window as unknown as { __socraSceneMetrics?: SceneMetrics }).__socraSceneMetrics = sceneMetrics
}
