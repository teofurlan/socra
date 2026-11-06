import { describe, expect, it } from 'vitest'
import { captionOf, hashLine, lastKey, summaryOf, touchedParts, visibleStructureViews } from '@/lib/sceneStructure'
import type { SceneObject } from '@/types/scene'

function object(kind: string, initial: Record<string, unknown>, over: Partial<SceneObject> = {}): SceneObject {
  return { id: 'ds', primitive: 'structure', hidden: false, params: { kind, items: [], initial }, ...over }
}

function view(kind: string, state: Record<string, unknown>) {
  const [v] = visibleStructureViews([object(kind, { kind, last: null })], { ds: { visible: true, kind, ...state } as never })
  return v
}

describe('visibleStructureViews', () => {
  it('reads the initial state from the params before the first step speaks', () => {
    const [v] = visibleStructureViews([object('stack', { kind: 'stack', items: [1, 2], last: null })], null)
    expect(v).toMatchObject({ id: 'ds', kind: 'stack', items: [1, 2], last: null })
  })

  it('reads the state of the current step once it exists', () => {
    const v = view('stack', { items: [1, 2, 3], last: { op: 'push', index: 2, value: 3 } })
    expect(v.items).toEqual([1, 2, 3])
    expect(v.last).toEqual({ op: 'push', index: 2, value: 3 })
  })

  it('skips an object that is hidden, not a structure, or without a known kind', () => {
    const hidden = object('stack', { kind: 'stack', items: [] }, { hidden: true })
    expect(visibleStructureViews([hidden], null)).toEqual([])
    expect(visibleStructureViews([hidden], { ds: { visible: true, kind: 'stack', items: [] } })).toHaveLength(1)
    expect(visibleStructureViews([{ ...hidden, hidden: false, primitive: 'diagram' }], null)).toEqual([])
    expect(visibleStructureViews([object('graph', { kind: 'graph' })], null)).toEqual([])
    expect(visibleStructureViews([{ ...hidden, hidden: false, params: {} }], null)).toEqual([])
  })

  it('reads defensively: malformed items, buckets, nodes and last are dropped', () => {
    const v = view('tree', {
      items: [1, null, 'a', {}],
      buckets: [[1, {}], 'x'],
      nodes: [{ key: 5, parent: null, depth: 0, slot: 0 }, { key: 'x' }, null, { key: 6, parent: 5, depth: 1, slot: 1 }],
      hash: 'weird',
      last: { op: 'insert', key: 6, path: [5, 'x', 6], extra: 1 },
    })
    expect(v.items).toEqual([1, 'a'])
    expect(v.buckets).toEqual([[1], []])
    expect(v.nodes.map((n) => n.key)).toEqual([5, 6])
    expect(v.hash).toBe('mod')
    expect(v.last).toEqual({ op: 'insert', key: 6, path: [5, 6] })
    expect(view('array', { last: 'nope' }).last).toBeNull()
  })

  it('tells the same operation by its key', () => {
    expect(lastKey(null)).toBe('')
    expect(lastKey({ op: 'pop', index: 1, value: 2 })).toBe(lastKey({ op: 'pop', index: 1, value: 2 }))
    expect(lastKey({ op: 'pop', index: 1, value: 2 })).not.toBe(lastKey({ op: 'pop', index: 0, value: 2 }))
  })
})

describe('captionOf', () => {
  it('is empty before any operation', () => {
    expect(captionOf(view('array', { items: [1] }))).toBe('')
  })

  it('words an array operation', () => {
    expect(captionOf(view('array', { items: [1, 9], last: { op: 'set', index: 1, value: 9, previous: 3 } }))).toBe('set [1] = 9 (was 3)')
    expect(captionOf(view('array', { items: [3, 1], last: { op: 'swap', indexes: [0, 1] } }))).toBe('swap [0] and [1]')
    expect(captionOf(view('array', { items: [5, 3], last: { op: 'compare', indexes: [0, 1], result: 'greater' } }))).toBe('compare [0] > [1]: 5 > 3')
    expect(captionOf(view('array', { items: [5, 3], last: { op: 'highlight', indexes: [0, 1] } }))).toBe('highlight [0] [1]')
  })

  it('words stack and queue operations', () => {
    expect(captionOf(view('stack', { items: [1], last: { op: 'push', index: 0, value: 'a' } }))).toBe('push "a"')
    expect(captionOf(view('stack', { items: [], last: { op: 'pop', index: 0, value: 7 } }))).toBe('pop → 7')
    expect(captionOf(view('queue', { items: [2], last: { op: 'dequeue', index: 0, value: 1 } }))).toBe('dequeue → 1')
    expect(captionOf(view('queue', { items: [1], last: { op: 'peek', index: 0, value: 1 } }))).toBe('peek → 1')
  })

  it('shows how the hash reached the bucket, the collision and the probes', () => {
    const buckets = [[], [], [12, 7], [], []]
    expect(captionOf(view('hashTable', { buckets, last: { op: 'insert', key: 7, hash: 7, bucket: 2, position: 1, collision: true } }))).toBe(
      'insert 7: 7 mod 5 = bucket 2 · collision, chained after 1 key',
    )
    expect(captionOf(view('hashTable', { buckets, last: { op: 'lookup', key: 7, hash: 7, bucket: 2, position: 1, found: true, probes: 2 } }))).toBe(
      'lookup 7: 7 mod 5 = bucket 2 · found after 2 probes',
    )
    expect(captionOf(view('hashTable', { buckets, last: { op: 'lookup', key: 22, hash: 22, bucket: 2, position: null, found: false, probes: 2 } }))).toBe(
      'lookup 22: 22 mod 5 = bucket 2 · not found after 2 probes',
    )
    expect(captionOf(view('hashTable', { buckets, last: { op: 'remove', key: 7, hash: 7, bucket: 2, position: 1 } }))).toBe('remove 7: 7 mod 5 = bucket 2')
  })

  it('shows the charSum rule with its sum', () => {
    const v = view('hashTable', { hash: 'charSum', buckets: [[], [], [], []], last: { op: 'insert', key: 'ab', hash: 195, bucket: 3, position: 0, collision: false } })
    expect(hashLine(v, v.last!)).toBe('charSum("ab") = 195, 195 mod 4 = bucket 3')
    expect(captionOf(v)).toBe('insert "ab": charSum("ab") = 195, 195 mod 4 = bucket 3')
  })

  it('words a tree walk', () => {
    expect(captionOf(view('tree', { last: { op: 'insert', key: 6, path: [8, 3, 6] } }))).toBe('insert 6: 8 → 3 → 6')
    expect(captionOf(view('tree', { last: { op: 'lookup', key: 7, path: [8, 3, 6], found: false } }))).toBe('lookup 7: 8 → 3 → 6, not found')
    expect(captionOf(view('tree', { last: { op: 'lookup', key: 1, path: [], found: false } }))).toBe('lookup 1: not found')
    expect(captionOf(view('tree', { last: { op: 'highlight', key: 3, path: [8, 3] } }))).toBe('path to 3: 8 → 3')
  })
})

describe('touchedParts', () => {
  it('names what each operation touched in the drawing', () => {
    expect(touchedParts(view('array', { last: { op: 'set', index: 2, value: 1, previous: 0 } }))).toEqual(['cell:2'])
    expect(touchedParts(view('array', { last: { op: 'swap', indexes: [0, 3] } }))).toEqual(['cell:0', 'cell:3'])
    expect(touchedParts(view('stack', { last: { op: 'push', index: 4, value: 1 } }))).toEqual(['cell:4'])
    expect(touchedParts(view('queue', { last: { op: 'enqueue', index: 1, value: 1 } }))).toEqual(['cell:1'])
    expect(touchedParts(view('queue', { last: { op: 'peek', index: 0, value: 1 } }))).toEqual(['cell:0'])
  })

  it('leaves out an element that is gone', () => {
    expect(touchedParts(view('stack', { last: { op: 'pop', index: 1, value: 1 } }))).toEqual([])
    expect(touchedParts(view('queue', { last: { op: 'dequeue', index: 0, value: 1 } }))).toEqual([])
    expect(touchedParts(view('array', {}))).toEqual([])
  })

  it('points at the chain entry that was inserted or found, and at the bucket otherwise', () => {
    expect(touchedParts(view('hashTable', { last: { op: 'insert', key: 7, hash: 7, bucket: 2, position: 1, collision: true } }))).toEqual(['entry:2:1'])
    expect(touchedParts(view('hashTable', { last: { op: 'lookup', key: 7, hash: 7, bucket: 2, position: 0, found: true, probes: 1 } }))).toEqual(['entry:2:0'])
    expect(touchedParts(view('hashTable', { last: { op: 'lookup', key: 9, hash: 9, bucket: 4, position: null, found: false, probes: 0 } }))).toEqual(['bucket:4'])
    expect(touchedParts(view('hashTable', { last: { op: 'remove', key: 7, hash: 7, bucket: 2, position: 1 } }))).toEqual(['bucket:2'])
  })

  it('points at the last nodes of a tree path, at most four', () => {
    expect(touchedParts(view('tree', { last: { op: 'insert', key: 6, path: [8, 3, 6] } }))).toEqual(['node:8', 'node:3', 'node:6'])
    expect(touchedParts(view('tree', { last: { op: 'lookup', key: 9, path: [1, 2, 3, 4, 5, 9], found: true } }))).toHaveLength(4)
    expect(touchedParts(view('tree', { last: { op: 'lookup', key: 9, path: [1, 2, 3, 4, 5, 9], found: true } })).at(-1)).toBe('node:9')
  })
})

describe('summaryOf', () => {
  it('describes the contents for screen readers', () => {
    expect(summaryOf(view('stack', { items: [1, 2] }))).toBe('Stack (bottom to top): 1, 2')
    expect(summaryOf(view('queue', { items: [] }))).toBe('Queue (front to back): empty')
    expect(summaryOf(view('hashTable', { buckets: [[1], []] }))).toBe('Hash table, 2 buckets. bucket 0: 1; bucket 1: empty')
    expect(summaryOf(view('tree', { nodes: [{ key: 1, parent: null, depth: 0, slot: 0 }] }))).toBe('Binary search tree, keys in order: 1')
  })
})
