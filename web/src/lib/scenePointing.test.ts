import { describe, it, expect } from 'vitest'
import { pointedState } from './scenePointing'
import type { WalkthroughData } from '@/types/exam'
import type { PointTarget, SceneObject } from '@/types/scene'

const objects: SceneObject[] = [
  { id: 'src', primitive: 'code', params: { code: 'one\ntwo\nthree', language: 'python' }, hidden: false },
  { id: 'flow', primitive: 'diagram', hidden: false, params: { nodes: [{ id: 'api', label: 'API' }, { id: 'db', label: 'DB' }], edges: [{ from: 'api', to: 'db' }] } },
  { id: 'arr', primitive: 'structure', hidden: false, params: { kind: 'array', items: [4, 5], initial: { kind: 'array', items: [4, 5], last: null } } },
  { id: 'hash', primitive: 'structure', hidden: false, params: { kind: 'hashTable', initial: { kind: 'hashTable', hash: 'mod', buckets: [[1], []], last: null } } },
  { id: 'tree', primitive: 'structure', hidden: false, params: { kind: 'tree', initial: { kind: 'tree', nodes: [{ key: 5, parent: null, depth: 0, slot: 0 }], last: null } } },
]

const state = {
  src: { visible: true, lines: [1, 1] },
  flow: { visible: true, highlighted: ['api'], dimmed: ['db'], revealed: [], trace: [], notes: {} },
  arr: { visible: true, kind: 'array', items: [4, 5], last: null },
  hash: { visible: true, kind: 'hashTable', hash: 'mod', buckets: [[1], []], last: null },
  tree: { visible: true, kind: 'tree', nodes: [{ key: 5, parent: null, depth: 0, slot: 0 }], last: null },
}

function ended(pointing?: PointTarget[]): WalkthroughData {
  return {
    title: 'T', objects, total: 1, status: 'ended', reason: 'completed', pointing,
    step: { index: 1, total: 1, id: 's', say: 'x', state },
  }
}

describe('pointedState', () => {
  it('is the step state itself when nothing is pointed at', () => {
    expect(pointedState(ended())).toBe(state)
    expect(pointedState(ended([]))).toBe(state)
  })

  it('is null without a step', () => {
    expect(pointedState({ ...ended(), step: null })).toBeNull()
  })

  it('focuses the lines of a code target, replacing the previous focus', () => {
    expect(pointedState(ended([{ object: 'src', lines: [2, 3] }]))?.src.lines).toEqual([2, 3])
  })

  it('highlights a diagram node like a highlight cue does, and leaves the others alone', () => {
    const flow = pointedState(ended([{ object: 'flow', part: 'db' }]))?.flow
    expect(flow?.highlighted).toEqual(['db'])
    expect(flow?.dimmed).toEqual([])
  })

  it('marks structure parts as pointed', () => {
    const shown = pointedState(ended([{ object: 'arr', part: 'cell:1' }, { object: 'hash', part: 'entry:0:0' }, { object: 'tree', part: 'node:5' }]))
    expect(shown?.arr.pointed).toEqual(['cell:1'])
    expect(shown?.hash.pointed).toEqual(['entry:0:0'])
    expect(shown?.tree.pointed).toEqual(['node:5'])
  })

  it('emphasizes the whole object for a bare target', () => {
    const shown = pointedState(ended([{ object: 'src' }, { object: 'flow' }, { object: 'arr' }, { object: 'hash' }, { object: 'tree' }]))
    expect(shown?.src.lines).toEqual([1, 3])
    expect(shown?.flow.highlighted).toEqual(['api', 'db'])
    expect(shown?.arr.pointed).toEqual(['cell:0', 'cell:1'])
    expect(shown?.hash.pointed).toEqual(['bucket:0', 'entry:0:0', 'bucket:1'])
    expect(shown?.tree.pointed).toEqual(['node:5'])
  })

  it('ignores targets for objects that are unknown or hidden, and parts that do not exist', () => {
    const hidden = { ...ended([{ object: 'src', lines: [2, 2] }, { object: 'nope' }, { object: 'flow', part: 'ghost' }]), step: { index: 1, total: 1, id: 's', say: 'x', state: { ...state, src: { visible: false, lines: null } } } }
    const shown = pointedState(hidden)
    expect(shown?.src.lines).toBeNull()
    expect(shown?.flow.highlighted).toEqual(['api'])
  })

  it('does not change the stored state', () => {
    const before = JSON.stringify(state)
    pointedState(ended([{ object: 'src', lines: [2, 3] }, { object: 'arr', part: 'cell:0' }]))
    expect(JSON.stringify(state)).toBe(before)
  })
})
