import { describe, expect, it } from 'vitest'
import type { StructureView, TreeNode } from '@/lib/sceneStructure'
import { MIN_SCALE, cellWidth, fitScale, hashLayout, layoutOf, rowLayout, stackLayout, treeLayout } from '@/lib/structureLayout'

const node = (key: number, parent: number | null, depth: number, slot: number): TreeNode => ({ key, parent, depth, slot })

describe('cellWidth', () => {
  it('grows with the longest item within bounds', () => {
    expect(cellWidth([1, 2])).toBe(40)
    expect(cellWidth(['abcdefgh'])).toBeGreaterThan(cellWidth(['ab']))
    expect(cellWidth(['x'.repeat(40)])).toBe(100)
  })
})

describe('rowLayout', () => {
  it('puts every cell in one row when the room allows', () => {
    const layout = rowLayout([1, 2, 3], 600)
    expect(new Set(layout.cells.map((c) => c.y)).size).toBe(1)
    expect(layout.cells.map((c) => c.x)).toEqual([...layout.cells.map((c) => c.x)].sort((a, b) => a - b))
    expect(layout.width).toBeLessThanOrEqual(600)
  })

  it('wraps into rows when the room is narrow, never wider than the room', () => {
    const layout = rowLayout(Array.from({ length: 10 }, (_, i) => i), 200)
    expect(new Set(layout.cells.map((c) => c.y)).size).toBeGreaterThan(1)
    expect(layout.width).toBeLessThanOrEqual(200)
    expect(new Set(layout.cells.map((c) => `${c.x},${c.y}`)).size).toBe(10)
  })

  it('is deterministic and keeps one cell per item', () => {
    expect(rowLayout([1, 2], 300)).toEqual(rowLayout([1, 2], 300))
    expect(rowLayout([], 300).cells).toEqual([])
  })
})

describe('stackLayout', () => {
  it('puts the bottom lowest and leaves a spare row above the top', () => {
    const layout = stackLayout([1, 2, 3])
    const ys = layout.cells.map((c) => c.y)
    expect(ys[0]).toBeGreaterThan(ys[1])
    expect(ys[1]).toBeGreaterThan(ys[2])
    expect(layout.ghost.y).toBeLessThan(ys[2])
    expect(layout.baseY).toBeGreaterThan(ys[0])
  })
})

describe('hashLayout', () => {
  it('draws one row per bucket and chains entries left to right', () => {
    const layout = hashLayout([[], [4, 9, 14], [1]])
    expect(layout.rows).toHaveLength(3)
    expect(layout.rows.map((r) => r.entries.length)).toEqual([0, 3, 1])
    const xs = layout.rows[1].entries.map((e) => e.x)
    expect(xs).toEqual([...xs].sort((a, b) => a - b))
    expect(layout.rows[1].y).toBeGreaterThan(layout.rows[0].y)
    expect(layout.width).toBeGreaterThan(hashLayout([[], [4], [1]]).width)
  })
})

describe('treeLayout', () => {
  it('places nodes at the slot and depth the server computed', () => {
    const layout = treeLayout([node(3, 8, 1, 0), node(8, null, 0, 1), node(10, 8, 1, 2)])
    const at = Object.fromEntries(layout.nodes.map((n) => [n.key, n]))
    expect(at[3].cx).toBeLessThan(at[8].cx)
    expect(at[8].cx).toBeLessThan(at[10].cx)
    expect(at[8].y).toBeLessThan(at[3].y)
    expect(at[3].y).toBe(at[10].y)
    expect(layout.edges.map((e) => `${e.from}>${e.to}`).sort()).toEqual(['8>10', '8>3'])
  })

  it('draws no edge for a node whose parent is unknown', () => {
    expect(treeLayout([node(3, 99, 1, 0)]).edges).toEqual([])
    expect(treeLayout([]).nodes).toEqual([])
  })
})

describe('fitScale', () => {
  it('never scales up, scales down to fit, and stops at the legible minimum', () => {
    expect(fitScale({ width: 100, height: 100 }, { width: 400, height: 400 })).toBe(1)
    expect(fitScale({ width: 400, height: 100 }, { width: 340, height: 400 })).toBeCloseTo(0.85)
    expect(fitScale({ width: 1000, height: 100 }, { width: 100, height: 400 })).toBe(MIN_SCALE)
    expect(fitScale({ width: 0, height: 0 }, { width: 100, height: 100 })).toBe(1)
  })
})

describe('layoutOf', () => {
  const base: StructureView = { id: 'ds', kind: 'array', items: [1, 2], buckets: [], hash: 'mod', nodes: [], last: null }

  it('lays each kind out with its own layout', () => {
    expect(layoutOf(base, 400).kind).toBe('array')
    expect(layoutOf({ ...base, kind: 'queue' }, 400).kind).toBe('queue')
    expect(layoutOf({ ...base, kind: 'stack' }, 400).kind).toBe('stack')
    expect(layoutOf({ ...base, kind: 'hashTable', buckets: [[1], []] }, 400).kind).toBe('hashTable')
    expect(layoutOf({ ...base, kind: 'tree' }, 400).kind).toBe('tree')
  })

  it('leaves room for the text of an element that just left', () => {
    const popped = layoutOf({ ...base, kind: 'stack', items: [1], last: { op: 'pop', index: 1, value: 'abcdefgh' } }, 400)
    const plain = layoutOf({ ...base, kind: 'stack', items: [1] }, 400)
    expect(popped.layout.width).toBeGreaterThan(plain.layout.width)
  })
})
