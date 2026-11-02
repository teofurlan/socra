import { afterEach, describe, it, expect } from 'vitest'
import { sceneFigureSources, sceneHeadline } from './sceneFigures'
import type { WalkthroughData } from '@/types/exam'

const CODE = { id: 'src', primitive: 'code', params: { code: 'one\ntwo\nthree\nfour', language: 'python' }, hidden: false }

function scene(over: Partial<WalkthroughData> = {}, lines: [number, number] | null = [2, 3], visible = true): WalkthroughData {
  return {
    title: 'Adding',
    objects: [CODE],
    total: 2,
    step: { index: 1, total: 2, id: 'mid', say: 'The middle.', state: { src: { visible, lines } } },
    status: 'playing',
    reason: null,
    ...over,
  }
}

function rect(x: number, y: number, w: number, h: number): DOMRect {
  return { x, y, left: x, top: y, width: w, height: h, right: x + w, bottom: y + h, toJSON: () => ({}) } as DOMRect
}

/** A code pane for object ``src``: a scroll viewport and four 20px lines starting at ``top``. */
function mountPane(top: number, focused: number[]) {
  const pre = document.createElement('pre')
  pre.dataset.sceneObject = 'src'
  pre.getBoundingClientRect = () => rect(500, 100, 300, 200)
  for (let i = 0; i < 4; i++) {
    const span = document.createElement('span')
    if (focused.includes(i + 1)) span.dataset.focused = 'true'
    span.getBoundingClientRect = () => rect(500, top + i * 20, 300, 20)
    pre.appendChild(span)
  }
  document.body.appendChild(pre)
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('sceneFigureSources', () => {
  it('points at the focused lines of a code object while the scene plays', () => {
    const sources = sceneFigureSources(scene())
    expect(sources.map((s) => [s.id, s.role])).toEqual([['focus:src:2-3', 'pointer']])
  })

  it('keeps pointing while the scene is paused', () => {
    expect(sceneFigureSources(scene({ status: 'paused' }))).toHaveLength(1)
  })

  it('points at nothing without a focus, for a hidden object, once the scene ended, or without a scene', () => {
    expect(sceneFigureSources(scene({}, null))).toEqual([])
    expect(sceneFigureSources(scene({}, [2, 3], false))).toEqual([])
    expect(sceneFigureSources(scene({ status: 'ended' }))).toEqual([])
    expect(sceneFigureSources(scene({ step: null }))).toEqual([])
    expect(sceneFigureSources(null)).toEqual([])
  })

  it('boxes the focused lines on screen with a margin', () => {
    mountPane(120, [2, 3])
    const [source] = sceneFigureSources(scene())
    expect(source.box()).toEqual({ x: 494, y: 134, w: 312, h: 52 })
  })

  it('clips the box to the visible part of the code', () => {
    mountPane(40, [2, 3])
    const [source] = sceneFigureSources(scene())
    // Lines 2-3 span 60..100 on screen; the viewport starts at 100, so only the margin is left.
    expect(source.box()).toBeNull()
    document.body.innerHTML = ''
    mountPane(60, [2, 3])
    expect(sceneFigureSources(scene())[0].box()).toEqual({ x: 494, y: 100, w: 312, h: 26 })
  })

  it('has no box while the code pane is not on the page', () => {
    const [source] = sceneFigureSources(scene())
    expect(source.box()).toBeNull()
  })

  it('outlines its box with points spaced a few pixels apart, never too many', () => {
    const [source] = sceneFigureSources(scene())
    const small = source.build({ x: 0, y: 0, w: 312, h: 52 })
    expect(small.length).toBeGreaterThan(60)
    expect(small.length).toBeLessThan(140)
    expect(source.build({ x: 0, y: 0, w: 4000, h: 3000 }).length).toBeLessThanOrEqual(220)
  })
})

describe('headline figure', () => {
  const HEAD = { id: 'title', primitive: 'headline', params: { text: 'Hello' }, hidden: false }
  const withHeadline = (state: Record<string, unknown>, objects: unknown[] = [HEAD, CODE]) =>
    scene({ objects: objects as WalkthroughData['objects'], step: { index: 1, total: 2, id: 'mid', say: 'x', state } as WalkthroughData['step'] })

  it('leads with the visible headline, before the code focus', () => {
    const sources = sceneFigureSources(withHeadline({ title: { visible: true, text: 'Hello' }, src: { visible: true, lines: [2, 3] } }))
    expect(sources.map((s) => [s.id, s.role])).toEqual([['headline:title:Hello', 'lead'], ['focus:src:2-3', 'pointer']])
  })

  it('is absent when hidden, ended or without a step', () => {
    expect(sceneFigureSources(withHeadline({ title: { visible: false, text: 'Hello' } }))).toEqual([])
    expect(sceneFigureSources({ ...withHeadline({ title: { visible: true, text: 'Hello' } }), status: 'ended' })).toEqual([])
    expect(sceneFigureSources({ ...withHeadline({ title: { visible: true, text: 'Hello' } }), step: null })).toEqual([])
    expect(sceneHeadline(null)).toBeNull()
  })

  it('changes id when set changes the text', () => {
    const a = sceneFigureSources(withHeadline({ title: { visible: true, text: 'Hello' } }))[0].id
    const b = sceneFigureSources(withHeadline({ title: { visible: true, text: 'Bye' } }))[0].id
    expect(a).not.toBe(b)
  })

  it('uses only the first visible headline', () => {
    const second = { ...HEAD, id: 'other' }
    const w = withHeadline({ title: { visible: false, text: 'A' }, other: { visible: true, text: 'B' } }, [HEAD, second])
    expect(sceneFigureSources(w).map((s) => s.id)).toEqual(['headline:other:B'])
    expect(sceneHeadline(w)).toEqual({ id: 'other', text: 'B' })
  })

  it('has no box without a canvas to rasterize the text', () => {
    const stage = document.createElement('div')
    stage.className = 'voice-stage'
    document.body.appendChild(stage)
    const [source] = sceneFigureSources(withHeadline({ title: { visible: true, text: 'Hello' } }))
    expect(source.box()).toBeNull()
  })
})
