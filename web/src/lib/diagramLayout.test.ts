import { describe, expect, it } from 'vitest'
import { MIN_SCALE, fitScale, layoutDiagram, pickLayout, polylineLength, wrapLabel, type DiagramEdgeInput, type DiagramNodeInput } from '@/lib/diagramLayout'

const node = (id: string, label = id, group = ''): DiagramNodeInput => ({ id, label, group })
const edge = (from: string, to: string, label = ''): DiagramEdgeInput => ({ from, to, label })

const NODES = [node('a', 'Browser'), node('b', 'API'), node('c', 'Database'), node('d', 'Cache')]
const EDGES = [edge('a', 'b', 'GET'), edge('b', 'c'), edge('b', 'd')]

function overlaps(p: { x: number; y: number; width: number; height: number }, q: typeof p) {
  return p.x < q.x + q.width && q.x < p.x + p.width && p.y < q.y + q.height && q.y < p.y + p.height
}

describe('wrapLabel', () => {
  it('keeps a short label on one line and wraps a long one at spaces, at most two lines', () => {
    expect(wrapLabel('API', 22)).toEqual(['API'])
    const lines = wrapLabel('Authentication and session service', 22)
    expect(lines).toHaveLength(2)
    expect(lines.join(' ')).toBe('Authentication and session service')
    expect(lines.every((l) => l.length <= 22)).toBe(true)
  })

  it('breaks an unbroken word and ellipsizes what does not fit in two lines', () => {
    const lines = wrapLabel('x'.repeat(40), 22)
    expect(lines).toHaveLength(2)
    expect(lines[1].length).toBeLessThanOrEqual(22)
    expect(wrapLabel('word '.repeat(12).trim(), 12).at(-1)).toMatch(/…$/)
  })
})

describe('layoutDiagram', () => {
  it('places every node and edge without coordinates from the caller', () => {
    const layout = layoutDiagram(NODES, EDGES, 'LR')
    expect(layout.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c', 'd'])
    expect(layout.edges.map((e) => e.key)).toEqual(['a>b', 'b>c', 'b>d'])
    for (const n of layout.nodes) {
      expect(Number.isFinite(n.x) && Number.isFinite(n.y)).toBe(true)
      expect(n.x).toBeGreaterThanOrEqual(0)
      expect(n.y).toBeGreaterThanOrEqual(0)
      expect(n.x + n.width).toBeLessThanOrEqual(layout.width)
      expect(n.y + n.height).toBeLessThanOrEqual(layout.height)
    }
  })

  it('never overlaps two nodes', () => {
    const many = Array.from({ length: 15 }, (_, i) => node(`n${i}`, `Service number ${i}`))
    const links = many.slice(1).map((n, i) => edge(`n${Math.floor(i / 2)}`, n.id))
    for (const direction of ['TB', 'LR'] as const) {
      const { nodes } = layoutDiagram(many, links, direction)
      for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) expect(overlaps(nodes[i], nodes[j])).toBe(false)
    }
  })

  it('lays ranks left to right for LR and top to bottom for TB', () => {
    const lr = layoutDiagram(NODES, EDGES, 'LR')
    const at = (id: string) => lr.nodes.find((n) => n.id === id)!
    expect(at('a').x).toBeLessThan(at('b').x)
    expect(at('b').x).toBeLessThan(at('c').x)
    const tb = layoutDiagram(NODES, EDGES, 'TB')
    const down = (id: string) => tb.nodes.find((n) => n.id === id)!
    expect(down('a').y).toBeLessThan(down('b').y)
    expect(down('b').y).toBeLessThan(down('c').y)
    expect(tb.width).toBeLessThan(tb.height * 2)
  })

  it('gives each edge a polyline that starts at its source and ends at its target', () => {
    const layout = layoutDiagram(NODES, EDGES, 'LR')
    const box = (id: string) => layout.nodes.find((n) => n.id === id)!
    const near = (p: { x: number; y: number }, n: ReturnType<typeof box>) =>
      p.x >= n.x - 1 && p.x <= n.x + n.width + 1 && p.y >= n.y - 1 && p.y <= n.y + n.height + 1
    for (const e of layout.edges) {
      expect(e.points.length).toBeGreaterThanOrEqual(2)
      expect(near(e.points[0], box(e.from))).toBe(true)
      expect(near(e.points[e.points.length - 1], box(e.to))).toBe(true)
    }
  })

  it('positions an edge label on the edge and not at the origin', () => {
    const layout = layoutDiagram(NODES, EDGES, 'LR')
    const labelled = layout.edges.find((e) => e.key === 'a>b')!
    expect(labelled.label).toBe('GET')
    expect(labelled.labelAt).not.toBeNull()
    expect(layout.edges.find((e) => e.key === 'b>c')!.labelAt).toBeNull()
  })

  it('keeps the two directions of a pair of nodes apart and handles cycles', () => {
    const layout = layoutDiagram([node('a'), node('b')], [edge('a', 'b', 'ask'), edge('b', 'a', 'answer')], 'LR')
    expect(layout.edges).toHaveLength(2)
    const [first, second] = layout.edges
    expect(first.points).not.toEqual(second.points)
    expect(Number.isFinite(layout.width) && layout.width > 0).toBe(true)
  })

  it('lays out nodes without edges and a single node', () => {
    const lone = layoutDiagram([node('only', 'Alone')], [], 'TB')
    expect(lone.nodes).toHaveLength(1)
    expect(lone.edges).toEqual([])
    const apart = layoutDiagram([node('a'), node('b'), node('c')], [], 'LR')
    expect(apart.nodes).toHaveLength(3)
  })

  it('sizes a node by its label and tags the group', () => {
    const { nodes } = layoutDiagram([node('a', 'A', 'client'), node('b', 'A much longer label here')], [], 'LR')
    expect(nodes[0].group).toBe('client')
    expect(nodes[1].width).toBeGreaterThan(nodes[0].width)
  })

  it('is deterministic', () => {
    expect(layoutDiagram(NODES, EDGES, 'LR')).toEqual(layoutDiagram(NODES, EDGES, 'LR'))
  })

  it('lays out the cap of 25 nodes', () => {
    const many = Array.from({ length: 25 }, (_, i) => node(`n${i}`))
    const layout = layoutDiagram(many, many.slice(1).map((n, i) => edge(`n${i}`, n.id)), 'TB')
    expect(layout.nodes).toHaveLength(25)
  })
})

describe('fitScale and pickLayout', () => {
  it('scales down to fit and never up past 1.15', () => {
    expect(fitScale({ width: 1000, height: 500 }, 500, 500)).toBeCloseTo(0.5)
    expect(fitScale({ width: 100, height: 50 }, 800, 600)).toBe(1.15)
  })

  it('keeps the asked direction when it fits as well, and turns a wide chain to TB on a narrow panel', () => {
    const chain = Array.from({ length: 6 }, (_, i) => node(`n${i}`, `Step ${i}`))
    const links = chain.slice(1).map((n, i) => edge(`n${i}`, n.id))
    expect(pickLayout(chain, links, 'LR', 1200, 500).direction).toBe('LR')
    const narrow = pickLayout(chain, links, 'LR', 300, 480)
    expect(narrow.direction).toBe('TB')
    expect(narrow.scale).toBeGreaterThan(fitScale(layoutDiagram(chain, links, 'LR'), 300, 480))
  })

  it('scrolls down rather than sideways when the floor makes the panel scroll', () => {
    const wide = Array.from({ length: 4 }, (_, i) => node(`n${i}`, `Service number ${i}`))
    const links = wide.slice(1).map((n, i) => edge(`n${i}`, n.id, 'calls the next one'))
    const picked = pickLayout(wide, links, 'LR', 260, 120)
    expect(picked.direction).toBe('TB')
    expect(picked.width * picked.scale).toBeLessThanOrEqual(260)
  })

  it('does not scale below the legibility floor; the panel scrolls instead', () => {
    const many = Array.from({ length: 25 }, (_, i) => node(`n${i}`, `Service ${i}`))
    const picked = pickLayout(many, [], 'LR', 300, 300)
    expect(picked.scale).toBeGreaterThanOrEqual(MIN_SCALE)
  })
})

describe('polylineLength', () => {
  it('adds the segments', () => {
    expect(polylineLength([{ x: 0, y: 0 }, { x: 3, y: 4 }, { x: 3, y: 10 }])).toBe(11)
    expect(polylineLength([{ x: 1, y: 1 }])).toBe(0)
  })
})
