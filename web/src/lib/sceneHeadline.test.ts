import { afterEach, describe, it, expect, vi } from 'vitest'
import type { WalkthroughData } from '@/types/exam'

const textFigure = vi.fn()
vi.mock('@/lib/particleFigures', () => ({ textFigure: (...a: unknown[]) => textFigure(...a), outlinePoints: () => [] }))

import { sceneFigureSources } from './sceneFigures'

const walkthrough: WalkthroughData = {
  title: 't',
  objects: [{ id: 'title', primitive: 'headline', params: { text: 'Hi' }, hidden: false }],
  total: 1,
  step: { index: 1, total: 1, id: 's', say: 'x', state: { title: { visible: true, text: 'Hi' } } },
  status: 'playing',
  reason: null,
}

function mountStage(w: number, h: number, x = 100, y = 50) {
  const stage = document.createElement('div')
  stage.className = 'voice-stage'
  stage.getBoundingClientRect = () => ({ x, y, left: x, top: y, width: w, height: h, right: x + w, bottom: y + h, toJSON: () => ({}) }) as DOMRect
  document.body.appendChild(stage)
}

afterEach(() => {
  document.body.innerHTML = ''
  textFigure.mockReset()
})

describe('headline box', () => {
  it('is null when the stage is missing', () => {
    textFigure.mockReturnValue({ points: [], aspect: 4 })
    expect(sceneFigureSources(walkthrough)[0].box()).toBeNull()
  })

  it('is width-limited for a wide text, centred on the stage', () => {
    textFigure.mockReturnValue({ points: [], aspect: 4 })
    mountStage(400, 400)
    const box = sceneFigureSources(walkthrough)[0].box()!
    expect(box.w).toBeCloseTo(360)
    expect(box.h).toBeCloseTo(90)
    expect(box.x + box.w / 2).toBeCloseTo(300)
    expect(box.y + box.h / 2).toBeCloseTo(250)
  })

  it('is a flat lead figure: it does not opt in to the 3D projection', () => {
    const source = sceneFigureSources(walkthrough)[0]
    expect(source.role).toBe('lead')
    expect(source.depth).toBeFalsy()
  })

  it('is height-limited for a tall text', () => {
    textFigure.mockReturnValue({ points: [], aspect: 1 })
    mountStage(400, 200)
    const box = sceneFigureSources(walkthrough)[0].box()!
    expect(box.h).toBeCloseTo(140)
    expect(box.w).toBeCloseTo(140)
  })

  it('rasterizes once, with the UI font', () => {
    const points = [{ x: 0, y: 0 }]
    textFigure.mockReturnValue({ points, aspect: 2 })
    mountStage(400, 400)
    const source = sceneFigureSources(walkthrough)[0]
    source.box()
    source.box()
    expect(source.build({ x: 0, y: 0, w: 1, h: 1 })).toBe(points)
    expect(textFigure).toHaveBeenCalledTimes(1)
    expect(textFigure.mock.calls[0][0]).toBe('Hi')
    expect(textFigure.mock.calls[0][1]).toBe(1260)
    expect(String(textFigure.mock.calls[0][2])).toContain('Geist')
  })
})
