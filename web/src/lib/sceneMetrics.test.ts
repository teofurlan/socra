import { describe, expect, it } from 'vitest'
import { createSceneMetrics } from '@/lib/sceneMetrics'

describe('scene metrics', () => {
  it('measures present to the first visual, once per scene', () => {
    const metrics = createSceneMetrics()
    metrics.present(100)
    metrics.firstVisual(340)
    metrics.firstVisual(900)
    expect(metrics.snapshot().firstVisualMs).toBe(240)
  })

  it('has no first visual before present', () => {
    const metrics = createSceneMetrics()
    metrics.firstVisual(50)
    expect(metrics.snapshot().firstVisualMs).toBeNull()
  })

  it('measures the drift from a step audio start to its cue being applied', () => {
    const metrics = createSceneMetrics()
    metrics.present(0)
    metrics.audioStart(1, 1000)
    metrics.cueApplied(1, 1012)
    metrics.audioStart(2, 2000)
    metrics.cueApplied(2, 2030)
    expect(metrics.snapshot().drifts).toEqual([
      { step: 1, ms: 12 },
      { step: 2, ms: 30 },
    ])
  })

  it('ignores a cue that has no audio start, and counts each audio start once', () => {
    const metrics = createSceneMetrics()
    metrics.present(0)
    metrics.cueApplied(1, 5)
    metrics.audioStart(2, 100)
    metrics.cueApplied(2, 110)
    metrics.cueApplied(2, 400)
    expect(metrics.snapshot().drifts).toEqual([{ step: 2, ms: 10 }])
  })

  it('starts over with a new scene', () => {
    const metrics = createSceneMetrics()
    metrics.present(0)
    metrics.audioStart(1, 10)
    metrics.cueApplied(1, 12)
    metrics.present(500)
    expect(metrics.snapshot()).toEqual({ firstVisualMs: null, drifts: [] })
  })
})
