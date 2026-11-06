import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PRIMITIVE_RENDERERS, hasScenePanel, panelObjects } from '@/components/scene/registry'
import { StructureObject } from '@/components/scene/StructureObject'
import type { SceneObject } from '@/types/scene'

function structure(kind: string, initial: Record<string, unknown>): SceneObject {
  return { id: 'ds', primitive: 'structure', hidden: false, params: { kind, items: [], initial: { kind, last: null, ...initial } } }
}

function draw(object: SceneObject, state: Record<string, unknown> | null, onClose = () => {}) {
  const props = { object, say: '', siblings: 1, name: 'walkthrough', onClose }
  const view = (s: Record<string, unknown> | null) => <StructureObject {...props} state={s ? ({ visible: true, kind: object.params.kind, ...s } as never) : null} />
  const result = render(view(state))
  return { ...result, again: (s: Record<string, unknown> | null) => result.rerender(view(s)) }
}

const part = (id: string) => document.querySelector(`[data-structure-part="${id}"]`)!
const parts = () => [...document.querySelectorAll('[data-structure-part]')].map((el) => el.getAttribute('data-structure-part'))
const root = () => document.querySelector('[data-structure-root]')!
const touched = () => [...document.querySelectorAll('[data-structure-part][data-touched="true"]')].map((el) => el.getAttribute('data-structure-part'))
const caption = () => document.querySelector('[data-structure-caption]')!.textContent

afterEach(() => vi.unstubAllGlobals())

function reduceMotion(reduce: boolean) {
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: reduce && query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }))
}

/** The drawing as text, attributes sorted: the same picture however its attributes were set. */
function picture(el: Element): string {
  const walk = (node: Element): string =>
    `<${node.tagName}${[...node.attributes].sort((a, b) => a.name.localeCompare(b.name)).map((a) => ` ${a.name}="${a.value}"`).join('')}>${[...node.childNodes]
      .map((n) => (n.nodeType === 1 ? walk(n as Element) : (n.textContent ?? '')))
      .join('')}`
  return walk(el)
}

describe('array', () => {
  const array = structure('array', { items: [5, 3, 8] })

  it('draws a cell with its value and index before the first step speaks', () => {
    draw(array, null)
    expect(screen.getByRole('region', { name: 'Walkthrough structure' })).toBeInTheDocument()
    expect(parts()).toEqual(['cell:0', 'cell:1', 'cell:2'])
    expect(part('cell:1').textContent).toBe('31')
    expect(root()).toHaveAttribute('data-kind', 'array')
    expect(root()).toHaveAccessibleName('Array: 5, 3, 8')
    expect(touched()).toEqual([])
  })

  it('swaps by sliding each cell from the other one, and outlines both', () => {
    draw(array, { items: [3, 5, 8], last: { op: 'swap', indexes: [0, 1] } })
    expect(touched()).toEqual(['cell:0', 'cell:1'])
    expect(part('cell:0')).toHaveAttribute('data-anim', 'slide')
    const a = (part('cell:0') as SVGElement).style
    const b = (part('cell:1') as SVGElement).style
    expect(parseFloat(a.getPropertyValue('--dx'))).toBeGreaterThan(0) // the left cell starts where the right one is
    expect(parseFloat(a.getPropertyValue('--dx'))).toBe(-parseFloat(b.getPropertyValue('--dx')))
    expect(caption()).toBe('swap [0] and [1]')
  })

  it('flashes the cells of a compare and pulses a highlight', () => {
    draw(array, { items: [5, 3, 8], last: { op: 'compare', indexes: [0, 1], result: 'greater' } })
    expect(part('cell:0')).toHaveAttribute('data-anim', 'flash')
    expect(caption()).toBe('compare [0] > [1]: 5 > 3')
    draw(array, { items: [5, 3, 8], last: { op: 'highlight', indexes: [2] } })
    expect(document.querySelectorAll('[data-structure-part="cell:2"][data-anim="pulse"]')).toHaveLength(1)
  })

  it('wraps its cells into rows in a narrow panel', () => {
    class Observer {
      callback: ResizeObserverCallback
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback
      }
      observe(target: Element) {
        this.callback([{ target, contentRect: { width: 200, height: 480 } } as ResizeObserverEntry], this as unknown as ResizeObserver)
      }
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal('ResizeObserver', Observer)
    draw(structure('array', { items: Array.from({ length: 10 }, (_, i) => i) }), null)
    const ys = new Set([...document.querySelectorAll('[data-structure-part] rect')].map((r) => r.getAttribute('y')))
    expect(ys.size).toBeGreaterThan(1)
    expect(parseFloat(root().getAttribute('width')!)).toBeLessThanOrEqual(200)
  })
})

describe('stack', () => {
  const stack = structure('stack', { items: [1, 2] })

  it('draws the top last and labels it', () => {
    draw(stack, null)
    expect(parts()).toEqual(['cell:0', 'cell:1'])
    expect(screen.getByText('top')).toBeInTheDocument()
    expect(root()).toHaveAccessibleName('Stack (bottom to top): 1, 2')
  })

  it('drops a pushed cell in from above', () => {
    draw(stack, { items: [1, 2, 3], last: { op: 'push', index: 2, value: 3 } })
    expect(touched()).toEqual(['cell:2'])
    expect(part('cell:2')).toHaveAttribute('data-anim', 'enter')
    expect(parseFloat((part('cell:2') as SVGElement).style.getPropertyValue('--dy'))).toBeLessThan(0)
    expect(caption()).toBe('push 3')
  })

  it('shows the popped cell leaving, and nothing is outlined', () => {
    draw(stack, { items: [1], last: { op: 'pop', index: 1, value: 2 } })
    expect(parts()).toEqual(['cell:0'])
    const ghost = document.querySelector('[data-structure-ghost]')!
    expect(ghost.textContent).toBe('2')
    expect(ghost).toHaveAttribute('data-anim', 'leave')
    expect(touched()).toEqual([])
    expect(caption()).toBe('pop → 2')
  })

  it('draws an empty stack as an empty slot', () => {
    draw(stack, { items: [] })
    expect(parts()).toEqual([])
    expect(document.querySelector('[data-structure-empty]')).not.toBeNull()
  })
})

describe('queue', () => {
  const queue = structure('queue', { items: ['a', 'b'] })

  it('labels the front and the back', () => {
    draw(queue, null)
    expect(screen.getByText('front')).toBeInTheDocument()
    expect(screen.getByText('back')).toBeInTheDocument()
    expect(root()).toHaveAccessibleName('Queue (front to back): a, b')
  })

  it('slides an enqueued cell in from the back and shows the dequeued one leaving', () => {
    draw(queue, { items: ['a', 'b', 'c'], last: { op: 'enqueue', index: 2, value: 'c' } })
    expect(part('cell:2')).toHaveAttribute('data-anim', 'enter')
    expect(parseFloat((part('cell:2') as SVGElement).style.getPropertyValue('--dx'))).toBeGreaterThan(0)
    draw(queue, { items: ['b'], last: { op: 'dequeue', index: 0, value: 'a' } })
    expect(document.querySelectorAll('[data-structure-ghost]')).toHaveLength(1)
  })

  it('labels a single element as both ends', () => {
    draw(queue, { items: ['a'] })
    expect(screen.getByText('front · back')).toBeInTheDocument()
  })
})

describe('hash table', () => {
  const table = structure('hashTable', { hash: 'mod', buckets: [[], [], [12, 7], [], []] })
  const collide = { op: 'insert', key: 7, hash: 7, bucket: 2, position: 1, collision: true }

  it('draws a row per bucket with its chain', () => {
    draw(table, null)
    expect(document.querySelectorAll('[data-structure-row]')).toHaveLength(5)
    expect(parts().filter((p) => p!.startsWith('entry:'))).toEqual(['entry:2:0', 'entry:2:1'])
    expect(document.querySelectorAll('.structure-link')).toHaveLength(1)
    expect(root()).toHaveAccessibleName(/bucket 2: 12, 7/)
  })

  it('shows a collision: the key chained after the one already there, in a marked bucket', () => {
    draw(table, { hash: 'mod', buckets: [[], [], [12, 7], [], []], last: collide })
    expect(document.querySelector('[data-structure-row="2"]')).toHaveAttribute('data-collision', 'true')
    expect(document.querySelector('[data-structure-row="1"]')).not.toHaveAttribute('data-collision')
    expect(touched()).toEqual(['entry:2:1'])
    expect(part('entry:2:1')).toHaveAttribute('data-anim', 'enter')
    expect(caption()).toBe('insert 7: 7 mod 5 = bucket 2 · collision, chained after 1 key')
  })

  it('does not mark a bucket as a collision when the key was alone', () => {
    draw(table, { hash: 'mod', buckets: [[], [3], [], [], []], last: { op: 'insert', key: 3, hash: 3, bucket: 3, position: 0, collision: false } })
    expect(document.querySelector('[data-structure-collision="true"]')).toBeNull()
    expect(document.querySelectorAll('[data-collision]')).toHaveLength(0)
  })

  it('walks the chain on a lookup, probe after probe', () => {
    draw(table, { hash: 'mod', buckets: [[], [], [12, 7], [], []], last: { op: 'lookup', key: 7, hash: 7, bucket: 2, position: 1, found: true, probes: 2 } })
    const delay = (id: string) => parseFloat((part(id) as SVGElement).style.getPropertyValue('--delay'))
    expect(part('entry:2:0')).toHaveAttribute('data-anim', 'probe')
    expect(delay('entry:2:1')).toBeGreaterThan(delay('entry:2:0'))
    expect(touched()).toEqual(['entry:2:1'])
  })

  it('outlines the bucket row when the key is not there', () => {
    draw(table, { hash: 'mod', buckets: [[], [], [12, 7], [], []], last: { op: 'lookup', key: 22, hash: 22, bucket: 2, position: null, found: false, probes: 2 } })
    expect(touched()).toEqual(['bucket:2'])
    expect(caption()).toBe('lookup 22: 22 mod 5 = bucket 2 · not found after 2 probes')
  })

  it('shows a removed key leaving its chain', () => {
    draw(table, { hash: 'mod', buckets: [[], [], [12], [], []], last: { op: 'remove', key: 7, hash: 7, bucket: 2, position: 1 } })
    expect(document.querySelector('[data-structure-ghost]')!.textContent).toBe('7')
  })
})

describe('tree', () => {
  const nodes = [
    { key: 1, parent: 3, depth: 2, slot: 0 },
    { key: 3, parent: 8, depth: 1, slot: 1 },
    { key: 6, parent: 3, depth: 2, slot: 2 },
    { key: 8, parent: null, depth: 0, slot: 3 },
    { key: 10, parent: 8, depth: 1, slot: 4 },
  ]
  const tree = structure('tree', { nodes })

  it('draws every node and an edge to each child, from the server positions', () => {
    draw(tree, null)
    expect(parts()).toEqual(['node:1', 'node:3', 'node:6', 'node:8', 'node:10'])
    expect(document.querySelectorAll('[data-structure-edge]')).toHaveLength(4)
    const y = (key: number) => parseFloat(part(`node:${key}`).querySelector('rect')!.getAttribute('y')!)
    const x = (key: number) => parseFloat(part(`node:${key}`).querySelector('rect')!.getAttribute('x')!)
    expect(y(8)).toBeLessThan(y(3))
    expect(y(3)).toBe(y(10))
    expect(x(1)).toBeLessThan(x(3))
    expect(x(3)).toBeLessThan(x(8))
    expect(root()).toHaveAccessibleName('Binary search tree, keys in order: 1, 3, 6, 8, 10')
  })

  it('lights the path node by node, in order, and the new node arrives last', () => {
    draw(tree, { nodes, last: { op: 'insert', key: 6, path: [8, 3, 6] } })
    const delay = (key: number) => parseFloat((part(`node:${key}`) as SVGElement).style.getPropertyValue('--delay'))
    expect(delay(8)).toBe(0)
    expect(delay(3)).toBeGreaterThan(delay(8))
    expect(delay(6)).toBeGreaterThan(delay(3))
    expect(part('node:8')).toHaveAttribute('data-anim', 'probe')
    expect(part('node:6')).toHaveAttribute('data-anim', 'enter')
    expect(part('node:10')).not.toHaveAttribute('data-anim')
    expect(touched().sort()).toEqual(['node:3', 'node:6', 'node:8'])
    expect(caption()).toBe('insert 6: 8 → 3 → 6')
  })

  it('does not animate a node outside the path', () => {
    draw(tree, { nodes, last: { op: 'lookup', key: 7, path: [8, 3, 6], found: false } })
    expect(part('node:1')).not.toHaveAttribute('data-anim')
    expect(part('node:6')).toHaveAttribute('data-anim', 'probe')
  })

  it('draws an empty tree as an empty slot', () => {
    draw(structure('tree', { nodes: [] }), null)
    expect(document.querySelector('[data-structure-empty]')).not.toBeNull()
  })
})

describe('motion', () => {
  const stack = structure('stack', { items: [1, 2] })
  const pushed = { items: [1, 2, 3], last: { op: 'push', index: 2, value: 3 } }

  it('plays animations with full motion', () => {
    draw(stack, pushed)
    expect(root()).toHaveAttribute('data-motion', 'full')
    expect(part('cell:2')).toHaveAttribute('data-anim', 'enter')
  })

  it('shows the final state at once under reduced motion: no animation and no leaving element', () => {
    reduceMotion(true)
    draw(stack, pushed)
    expect(root()).toHaveAttribute('data-motion', 'reduced')
    expect(document.querySelectorAll('[data-anim]')).toHaveLength(0)
    expect(touched()).toEqual(['cell:2'])
    draw(stack, { items: [1], last: { op: 'pop', index: 1, value: 2 } })
    expect(document.querySelector('[data-structure-ghost]')).toBeNull()
    draw(structure('tree', { nodes: [{ key: 1, parent: null, depth: 0, slot: 0 }] }), { nodes: [{ key: 1, parent: null, depth: 0, slot: 0 }], last: { op: 'lookup', key: 1, path: [1], found: true } })
    expect(document.querySelectorAll('[data-anim]')).toHaveLength(0)
  })

  it('follows a change of the reduced-motion preference while drawn', () => {
    let reduce = false
    const listeners = new Set<() => void>()
    vi.stubGlobal('matchMedia', (query: string) => ({
      get matches() { return reduce && query.includes('reduce') },
      media: query,
      addEventListener: (_: string, fn: () => void) => listeners.add(fn),
      removeEventListener: (_: string, fn: () => void) => listeners.delete(fn),
    }))
    draw(stack, pushed)
    expect(root()).toHaveAttribute('data-motion', 'full')
    reduce = true
    act(() => listeners.forEach((fn) => fn()))
    expect(root()).toHaveAttribute('data-motion', 'reduced')
    expect(document.querySelectorAll('[data-anim]')).toHaveLength(0)
  })

  it('plays the operation again when it changes, but not when only another step passes with the same state', () => {
    const { again, container } = draw(stack, pushed)
    const before = part('cell:2')
    again({ ...pushed })
    expect(part('cell:2')).toBe(before)
    again({ items: [1, 2, 3, 4], last: { op: 'push', index: 3, value: 4 } })
    expect(part('cell:3')).toHaveAttribute('data-anim', 'enter')
    expect(part('cell:2')).not.toHaveAttribute('data-anim')
    expect(container.querySelectorAll('[data-anim="enter"]')).toHaveLength(1)
  })
})

describe('going back', () => {
  it('returns to exactly the earlier picture when the earlier state comes back', () => {
    const { again, container } = draw(structure('queue', { items: ['a', 'b'] }), { items: ['a', 'b', 'c'], last: { op: 'enqueue', index: 2, value: 'c' } })
    const first = picture(container)
    again({ items: ['b', 'c'], last: { op: 'dequeue', index: 0, value: 'a' } })
    expect(picture(container)).not.toBe(first)
    again({ items: ['a', 'b', 'c'], last: { op: 'enqueue', index: 2, value: 'c' } })
    expect(picture(container)).toBe(first)
  })
})

describe('panel', () => {
  it('names the panel, counts the items and closes from its button', () => {
    const onClose = vi.fn()
    draw(structure('hashTable', { hash: 'mod', buckets: [[1], [2], []] }), null, onClose)
    expect(screen.getByText('Hash table')).toBeInTheDocument()
    expect(screen.getByText('3 buckets, 2 items')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Close structure' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('draws nothing for a structure without a known kind', () => {
    const { container } = draw({ id: 'ds', primitive: 'structure', hidden: false, params: {} }, null)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('registry', () => {
  const stack = structure('stack', { items: [1] })

  it('registers the structure, visible while shown and drawn in the panel', () => {
    expect(PRIMITIVE_RENDERERS.structure).toBeDefined()
    expect(hasScenePanel([stack], null)).toBe(true)
    expect(hasScenePanel([stack], { ds: { visible: false } })).toBe(false)
    expect(panelObjects([stack], { ds: { visible: true, kind: 'stack', items: [1] } }, PRIMITIVE_RENDERERS)).toHaveLength(1)
  })

  it('does not treat a structure without a kind as drawable', () => {
    expect(hasScenePanel([{ ...stack, params: {} }], null)).toBe(false)
  })
})
