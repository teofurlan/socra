import { describe, expect, it } from 'vitest'
import { visibleDiagramViews } from '@/lib/sceneDiagram'
import type { SceneObject } from '@/types/scene'

const flow: SceneObject = {
  id: 'flow',
  primitive: 'diagram',
  hidden: false,
  params: {
    direction: 'TB',
    nodes: [{ id: 'a', label: 'A', group: 'x' }, { id: 'b', label: 'B', group: '' }, { id: 'c', label: 'C', group: '' }],
    edges: [{ from: 'a', to: 'b', label: 'go', hidden: false }, { from: 'b', to: 'c', label: '', hidden: true }],
  },
}

describe('visibleDiagramViews', () => {
  it('shows the declared edges that are not hidden before the first step', () => {
    const [view] = visibleDiagramViews([flow], null)
    expect(view.direction).toBe('TB')
    expect(view.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c'])
    expect([...view.revealed]).toEqual(['a>b'])
    expect(view.trace).toEqual([])
  })

  it('reads highlight, dim, revealed edges, trace and notes from the step state', () => {
    const [view] = visibleDiagramViews([flow], {
      flow: {
        visible: true,
        highlighted: ['a'],
        dimmed: ['c', 'ghost'],
        revealed: [{ from: 'a', to: 'b' }, { from: 'b', to: 'c' }],
        trace: ['a', 'b', 'c'],
        notes: { b: 'slow', ghost: 'x' },
      },
    })
    expect([...view.highlighted]).toEqual(['a'])
    expect([...view.dimmed]).toEqual(['c'])
    expect([...view.revealed]).toEqual(['a>b', 'b>c'])
    expect(view.trace).toEqual(['a', 'b', 'c'])
    expect(view.notes).toEqual({ b: 'slow' })
  })

  it('draws nothing while hidden, for other primitives, or without nodes', () => {
    expect(visibleDiagramViews([flow], { flow: { visible: false } })).toEqual([])
    expect(visibleDiagramViews([{ ...flow, hidden: true }], null)).toEqual([])
    expect(visibleDiagramViews([{ ...flow, primitive: 'code' }], null)).toEqual([])
    expect(visibleDiagramViews([{ ...flow, params: { nodes: 'x' } }], null)).toEqual([])
  })

  it('ignores malformed state instead of throwing', () => {
    const [view] = visibleDiagramViews([flow], { flow: { visible: true, highlighted: 'a', trace: [1, 'b'], notes: [], revealed: [null] } })
    expect(view.highlighted.size).toBe(0)
    expect(view.trace).toEqual(['b'])
    expect(view.notes).toEqual({})
    expect(view.revealed.size).toBe(0)
  })
})
