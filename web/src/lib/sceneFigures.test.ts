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

function mountStage(w: number, h: number, x = 100, y = 50) {
  const stage = document.createElement('div')
  stage.className = 'voice-stage'
  stage.getBoundingClientRect = () => rect(x, y, w, h)
  document.body.appendChild(stage)
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('sceneFigureSources', () => {
  it('points at the focused lines of a code object while the scene plays', () => {
    const sources = sceneFigureSources(scene())
    expect(sources.map((s) => [s.id, s.role])).toEqual([['focus:src:2-3', 'pointer']])
  })

  it('keeps pointing after the scene completed, but not after it was stopped', () => {
    expect(sceneFigureSources(scene({ status: 'ended', reason: 'completed' }))).toHaveLength(1)
    for (const reason of ['stopped', 'error', 'disconnected']) {
      expect(sceneFigureSources(scene({ status: 'ended', reason }))).toEqual([])
    }
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

  it('boxes the focused lines on screen with a margin above and below', () => {
    mountPane(120, [2, 3])
    const [source] = sceneFigureSources(scene())
    expect(source.box()).toEqual({ x: 500, y: 137, w: 300, h: 46 })
  })

  it('keeps the box inside the pane when the lines are wider than it', () => {
    mountPane(120, [2, 3])
    document.querySelectorAll<HTMLElement>('pre > span').forEach((span, i) => {
      span.getBoundingClientRect = () => rect(480, 120 + i * 20, 900, 20)
    })
    expect(sceneFigureSources(scene())[0].box()).toEqual({ x: 500, y: 137, w: 300, h: 46 })
  })

  it('clips the box to the visible part of the code', () => {
    mountPane(40, [2, 3])
    const [source] = sceneFigureSources(scene())
    // Lines 2-3 span 60..100 on screen; the viewport starts at 100, so only the margin is left.
    expect(source.box()).toBeNull()
    document.body.innerHTML = ''
    mountPane(60, [2, 3])
    expect(sceneFigureSources(scene())[0].box()).toEqual({ x: 500, y: 100, w: 300, h: 23 })
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

  it('stays after the scene completed and goes when it was stopped', () => {
    const shown = withHeadline({ title: { visible: true, text: 'Hello' } })
    expect(sceneHeadline({ ...shown, status: 'ended', reason: 'completed' })).toEqual({ id: 'title', text: 'Hello' })
    expect(sceneHeadline({ ...shown, status: 'ended', reason: 'stopped' })).toBeNull()
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

describe('shape figure', () => {
  const HEAD = { id: 'title', primitive: 'headline', params: { text: 'Hello' }, hidden: false }
  const CUBE = { id: 'body', primitive: 'shape', params: { shape: 'cube', wireframe: false }, hidden: false }
  const withShape = (state: Record<string, unknown>, objects: unknown[] = [CUBE, HEAD, CODE]) =>
    scene({ objects: objects as WalkthroughData['objects'], step: { index: 1, total: 2, id: 'mid', say: 'x', state } as WalkthroughData['step'] })
  const shown = { body: { visible: true, shape: 'cube', wireframe: false, rx: 0, ry: 0, rz: 0 } }

  it('is a lead figure that opts in to depth and carries the scene pose', () => {
    const [source] = sceneFigureSources(withShape({ body: { ...shown.body, rx: 0.35, ry: 0.25 } }))
    expect(source.id).toBe('shape:body:cube:solid')
    expect(source.role).toBe('lead')
    expect(source.depth).toBe(true)
    expect(source.pose).toEqual({ rx: 0.35, ry: 0.25, rz: 0 })
  })

  it('wins over a headline: while both are visible only the shape (and the code focus) is drawn', () => {
    const sources = sceneFigureSources(withShape({ ...shown, title: { visible: true, text: 'Hello' }, src: { visible: true, lines: [2, 3] } }))
    expect(sources.map((s) => [s.id, s.role])).toEqual([['shape:body:cube:solid', 'lead'], ['focus:src:2-3', 'pointer']])
  })

  it('gives the stage back to the headline once the shape is hidden', () => {
    const sources = sceneFigureSources(withShape({ body: { ...shown.body, visible: false }, title: { visible: true, text: 'Hello' } }))
    expect(sources.map((s) => s.id)).toEqual(['headline:title:Hello'])
    expect(sceneFigureSources(withShape({ body: { ...shown.body, visible: false } }))).toEqual([])
  })

  it('keeps its id (and so its particles) as the pose changes, and renews it when the solid changes', () => {
    const id = (state: Record<string, unknown>) => sceneFigureSources(withShape(state))[0].id
    expect(id({ body: { ...shown.body, ry: 0.5 } })).toBe(id(shown))
    expect(id({ body: { ...shown.body, shape: 'torus' } })).toBe('shape:body:torus:solid')
    expect(id({ body: { ...shown.body, wireframe: true } })).toBe('shape:body:cube:wire')
  })

  it('goes back to the earlier pose when an earlier step is shown again', () => {
    const at = (rx: number) => sceneFigureSources(withShape({ body: { ...shown.body, rx } }))[0].pose
    const first = at(0.1)
    at(0.6)
    expect(at(0.1)).toEqual(first)
  })

  it('stays after the scene completed and goes when it was stopped', () => {
    expect(sceneFigureSources({ ...withShape(shown), status: 'ended', reason: 'completed' }).map((x) => x.role)).toEqual(['lead'])
    expect(sceneFigureSources({ ...withShape(shown), status: 'ended', reason: 'stopped' })).toEqual([])
  })

  it('is absent once the scene ended or without a step', () => {
    expect(sceneFigureSources({ ...withShape(shown), status: 'ended' })).toEqual([])
    expect(sceneFigureSources({ ...withShape(shown), step: null })).toEqual([])
  })

  it('uses only the first visible shape', () => {
    const second = { ...CUBE, id: 'other' }
    const sources = sceneFigureSources(withShape({ body: shown.body, other: { ...shown.body, shape: 'cone' } }, [CUBE, second]))
    expect(sources.map((s) => s.id)).toEqual(['shape:body:cube:solid'])
  })

  it('boxes a square in the stage, small enough that perspective keeps it inside', () => {
    mountStage(600, 400)
    const [source] = sceneFigureSources(withShape(shown))
    const box = source.box()!
    expect(box.w).toBe(box.h)
    expect(box.h).toBeLessThan(400)
    expect(box.h).toBeGreaterThan(200)
    expect(box.x + box.w / 2).toBeCloseTo(400)
    expect(box.y + box.h / 2).toBeCloseTo(250)
    document.body.innerHTML = ''
    expect(source.box()).toBeNull()
  })

  it('builds the solid points of its kind and wireframe', () => {
    const [source] = sceneFigureSources(withShape(shown))
    const points = source.build({ x: 0, y: 0, w: 300, h: 300 })
    expect(points.length).toBeGreaterThan(500)
    expect(points.every((q) => q.nx !== undefined && q.z !== undefined)).toBe(true)
  })
})

const FLOW = {
  id: 'flow',
  primitive: 'diagram',
  hidden: false,
  params: {
    nodes: [{ id: 'a', label: 'A', group: '' }, { id: 'b', label: 'B', group: '' }, { id: 'c', label: 'C', group: '' }],
    edges: [{ from: 'a', to: 'b', label: '', hidden: false }, { from: 'b', to: 'c', label: '', hidden: false }],
  },
}

function flowScene(state: Record<string, unknown>, over: Partial<WalkthroughData> = {}): WalkthroughData {
  return {
    title: 'Flow',
    objects: [FLOW],
    total: 1,
    step: { index: 1, total: 1, id: 's', say: 'x', state: { flow: { visible: true, highlighted: [], dimmed: [], revealed: [], trace: [], notes: {}, ...state } } },
    status: 'playing',
    reason: null,
    ...over,
  }
}

/** A diagram's SVG: a viewport, node boxes and edge paths with given screen rectangles. */
function mountFlow(nodes: Record<string, DOMRect>, edges: Record<string, DOMRect>, view = rect(0, 0, 800, 600)) {
  const viewport = document.createElement('div')
  viewport.setAttribute('data-diagram-viewport', '')
  viewport.getBoundingClientRect = () => view
  const root = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  root.setAttribute('data-diagram-root', '')
  root.dataset.sceneObject = 'flow'
  for (const [id, box] of Object.entries(nodes)) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    g.setAttribute('data-diagram-node', id)
    const r = document.createElementNS('http://www.w3.org/2000/svg', 'rect')
    r.getBoundingClientRect = () => box
    g.appendChild(r)
    root.appendChild(g)
  }
  for (const [key, box] of Object.entries(edges)) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g')
    g.setAttribute('data-diagram-edge', key)
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    p.getBoundingClientRect = () => box
    g.appendChild(p)
    root.appendChild(g)
  }
  viewport.appendChild(root)
  document.body.appendChild(viewport)
}

describe('diagram pointing', () => {
  it('outlines each highlighted node as a pointer figure, and nothing without a highlight', () => {
    expect(sceneFigureSources(flowScene({}))).toEqual([])
    const sources = sceneFigureSources(flowScene({ highlighted: ['b', 'c'] }))
    expect(sources.map((s) => [s.id, s.role])).toEqual([['highlight:flow:b', 'pointer'], ['highlight:flow:c', 'pointer']])
    expect(sources.every((s) => !s.depth)).toBe(true)
  })

  it('boxes a highlighted node with a margin, clipped to the diagram viewport', () => {
    mountFlow({ b: rect(100, 100, 90, 40), c: rect(780, 100, 90, 40) }, {})
    const [b, c] = sceneFigureSources(flowScene({ highlighted: ['b', 'c'] }))
    expect(b.box()).toEqual({ x: 97, y: 97, w: 96, h: 46 })
    expect(c.box()).toEqual({ x: 777, y: 97, w: 23, h: 46 })
    const outlined = b.build(b.box()!)
    expect(outlined.length).toBeGreaterThan(20)
    expect(outlined.every((p) => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)).toBe(true)
  })

  it('has no box while the node is not on screen', () => {
    const [source] = sceneFigureSources(flowScene({ highlighted: ['b'] }))
    expect(source.box()).toBeNull()
    mountFlow({ b: rect(100, 100, 90, 40) }, {}, rect(0, 0, 50, 50))
    expect(source.box()).toBeNull()
  })

  it('outlines at most four highlighted nodes', () => {
    const many = { ...FLOW, params: { ...FLOW.params, nodes: ['a', 'b', 'c', 'd', 'e', 'f'].map((id) => ({ id, label: id, group: '' })), edges: [] } }
    const scene = flowScene({ highlighted: ['a', 'b', 'c', 'd', 'e', 'f'] }, { objects: [many] })
    expect(sceneFigureSources(scene)).toHaveLength(4)
  })

  it('follows the traced edges with one pointer figure whose box spans them', () => {
    mountFlow({}, { 'a>b': rect(100, 200, 80, 2), 'b>c': rect(180, 200, 80, 60) })
    const sources = sceneFigureSources(flowScene({ trace: ['a', 'b', 'c'] }))
    expect(sources.map((s) => [s.id, s.role])).toEqual([['trace:flow:a>b>c', 'pointer']])
    const box = sources[0].box()!
    expect(box).toEqual({ x: 96, y: 196, w: 168, h: 68 })
    const points = sources[0].build(box)
    expect(points.length).toBeGreaterThanOrEqual(8)
    expect(points.every((p) => p.x >= 0 && p.x <= 1 && p.y >= 0 && p.y <= 1)).toBe(true)
    // First edge's points come first: they sit left of the second edge's.
    expect(points[0].x).toBeLessThan(points[points.length - 1].x)
  })

  it('drops trace points outside the clipped viewport instead of piling them on its border', () => {
    mountFlow({}, { 'a>b': rect(100, 200, 200, 2) }, rect(0, 0, 160, 600))
    const [source] = sceneFigureSources(flowScene({ trace: ['a', 'b'] }))
    const box = source.box()!
    expect(box.x + box.w).toBe(160)
    const points = source.build(box)
    expect(points.length).toBeGreaterThan(0)
    expect(points.every((p) => p.x >= 0 && p.x <= 1)).toBe(true)
    expect(points.filter((p) => p.x === 1)).toHaveLength(0)
  })

  it('asks for a rebuild of the trace points when the diagram changes size on screen', () => {
    mountFlow({}, { 'a>b': rect(100, 200, 80, 60) })
    const [before] = sceneFigureSources(flowScene({ trace: ['a', 'b'] }))
    const first = before.rebuildKey?.(before.box()!)
    expect(first).toBeDefined()
    document.body.replaceChildren()
    mountFlow({}, { 'a>b': rect(100, 200, 160, 120) })
    const [after] = sceneFigureSources(flowScene({ trace: ['a', 'b'] }))
    expect(after.rebuildKey?.(after.box()!)).not.toBe(first)
    expect(after.id).toBe(before.id)
  })

  it('still boxes a straight edge that has no thickness', () => {
    mountFlow({}, { 'a>b': rect(100, 200, 80, 0) })
    const [source] = sceneFigureSources(flowScene({ trace: ['a', 'b'] }))
    const box = source.box()
    expect(box).not.toBeNull()
    expect(box!.h).toBeGreaterThanOrEqual(24)
    const points = source.build(box!)
    expect(points.length).toBeGreaterThanOrEqual(8)
    expect(points.every((p) => Math.abs(p.y - 0.5) < 0.01)).toBe(true)
  })

  it('a new trace is a new figure, so the particles are recruited again', () => {
    const one = sceneFigureSources(flowScene({ trace: ['a', 'b'] }))[0].id
    const two = sceneFigureSources(flowScene({ trace: ['a', 'b', 'c'] }))[0].id
    expect(one).not.toBe(two)
  })

  it('keeps pointing after the scene completed, but not once it was stopped', () => {
    expect(sceneFigureSources(flowScene({ highlighted: ['a'] }, { status: 'ended', reason: 'completed' }))).toHaveLength(1)
    expect(sceneFigureSources(flowScene({ highlighted: ['a'] }, { status: 'ended', reason: 'stopped' }))).toEqual([])
  })

  it('does not point at a hidden diagram', () => {
    const scene = flowScene({ highlighted: ['a'], visible: false })
    expect(sceneFigureSources(scene)).toEqual([])
  })
})
