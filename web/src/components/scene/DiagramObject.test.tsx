import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DiagramObject } from '@/components/scene/DiagramObject'
import { PRIMITIVE_RENDERERS, hasScenePanel, panelObjects } from '@/components/scene/registry'
import type { SceneObject } from '@/types/scene'

const flow: SceneObject = {
  id: 'flow',
  primitive: 'diagram',
  hidden: false,
  params: {
    direction: 'LR',
    nodes: [
      { id: 'browser', label: 'Browser', group: 'client' },
      { id: 'api', label: 'API', group: 'server' },
      { id: 'db', label: 'Database', group: 'server' },
      { id: 'cache', label: 'Cache', group: '' },
    ],
    edges: [
      { from: 'browser', to: 'api', label: 'GET /items', hidden: false },
      { from: 'api', to: 'db', label: '', hidden: false },
      { from: 'api', to: 'cache', label: '', hidden: true },
    ],
  },
}
const base = { visible: true, highlighted: [], dimmed: [], revealed: [{ from: 'browser', to: 'api' }, { from: 'api', to: 'db' }], trace: [], notes: {} }

function draw(state: Record<string, unknown> | null, onClose = () => {}) {
  return render(<DiagramObject object={flow} state={state ? ({ visible: true, ...state } as never) : null} say="" siblings={1} name="walkthrough" onClose={onClose} />)
}
const node = (id: string) => document.querySelector(`[data-diagram-node="${id}"]`)!
const edge = (key: string) => document.querySelector(`[data-diagram-edge="${key}"]`)!

afterEach(() => vi.unstubAllGlobals())

/** The drawing as text, attributes sorted: the same picture however its attributes were set. */
function picture(root: Element): string {
  const walk = (el: Element): string =>
    `<${el.tagName}${[...el.attributes].sort((a, b) => a.name.localeCompare(b.name)).map((a) => ` ${a.name}="${a.value}"`).join('')}>${[...el.childNodes]
      .map((n) => (n.nodeType === 1 ? walk(n as Element) : (n.textContent ?? '')))
      .join('')}`
  return walk(root)
}

describe('DiagramObject', () => {
  it('draws a region with a box and label per node and an arrow per revealed edge', () => {
    draw(base)
    expect(screen.getByRole('region', { name: 'Walkthrough diagram' })).toBeInTheDocument()
    for (const label of ['Browser', 'API', 'Database', 'Cache']) expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText('GET /items')).toBeInTheDocument()
    expect(edge('browser>api')).toHaveAttribute('data-revealed', 'true')
    expect(edge('api>cache')).toHaveAttribute('data-revealed', 'false')
    expect(document.querySelectorAll('[data-diagram-node]')).toHaveLength(4)
    expect(document.querySelector('[data-diagram-root]')).toHaveAttribute('data-scene-object', 'flow')
  })

  it('marks highlighted and dimmed nodes', () => {
    draw({ ...base, highlighted: ['api'], dimmed: ['cache'] })
    expect(node('api')).toHaveAttribute('data-highlighted', 'true')
    expect(node('api')).not.toHaveAttribute('data-dimmed')
    expect(node('cache')).toHaveAttribute('data-dimmed', 'true')
    expect(node('db')).not.toHaveAttribute('data-highlighted')
  })

  it('shows an annotation beside its node', () => {
    draw({ ...base, notes: { db: 'slow query' } })
    expect(screen.getByText('slow query')).toBeInTheDocument()
    expect(document.querySelector('[data-diagram-note="db"]')).not.toBeNull()
  })

  it('animates a trace edge by edge, in order', () => {
    draw({ ...base, revealed: [...base.revealed, { from: 'api', to: 'cache' }], trace: ['browser', 'api', 'cache'] })
    const traced = [...document.querySelectorAll('[data-diagram-edge][data-traced="true"]')]
    expect(traced.map((e) => e.getAttribute('data-diagram-edge'))).toEqual(['browser>api', 'api>cache'])
    const delays = traced.map((e) => parseFloat((e as HTMLElement).style.getPropertyValue('--trace-delay')))
    expect(delays[0]).toBe(0)
    expect(delays[1]).toBeGreaterThan(delays[0])
    expect(document.querySelector('[data-diagram-edge="api>db"]')).not.toHaveAttribute('data-traced')
    expect(node('cache')).toHaveAttribute('data-traced', 'true')
    expect(node('db')).not.toHaveAttribute('data-traced')
    expect(document.querySelector('[data-diagram-root]')).toHaveAttribute('data-motion', 'full')
  })

  it('shows the final state without animation under reduced motion', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce'), media: query, addEventListener() {}, removeEventListener() {} }))
    draw({ ...base, trace: ['browser', 'api', 'db'] })
    expect(document.querySelector('[data-diagram-root]')).toHaveAttribute('data-motion', 'reduced')
    for (const e of document.querySelectorAll('[data-diagram-edge][data-traced="true"]')) {
      expect((e as HTMLElement).style.getPropertyValue('--trace-delay')).toBe('0s')
      expect((e as HTMLElement).style.getPropertyValue('--trace-duration')).toBe('0s')
    }
    expect(document.querySelectorAll('[data-diagram-edge][data-traced="true"]')).toHaveLength(2)
  })

  it('returns to exactly the earlier picture when the earlier state comes back', () => {
    const { container, rerender } = draw({ ...base, highlighted: ['browser'] })
    const first = picture(container)
    const props = { object: flow, say: '', siblings: 1, name: 'walkthrough', onClose: () => {} }
    rerender(<DiagramObject {...props} state={{ ...base, highlighted: ['api'], trace: ['api', 'db'], notes: { db: 'x' } } as never} />)
    expect(picture(container)).not.toBe(first)
    rerender(<DiagramObject {...props} state={{ ...base, highlighted: ['browser'] } as never} />)
    expect(picture(container)).toBe(first)
  })

  it('draws a wide chain top to bottom when its panel is narrow', () => {
    const chain: SceneObject = {
      ...flow,
      params: {
        direction: 'LR',
        nodes: Array.from({ length: 6 }, (_, i) => ({ id: `n${i}`, label: `Step ${i}`, group: '' })),
        edges: Array.from({ length: 5 }, (_, i) => ({ from: `n${i}`, to: `n${i + 1}`, label: '', hidden: false })),
      },
    }
    class Observer {
      callback: ResizeObserverCallback
      constructor(callback: ResizeObserverCallback) {
        this.callback = callback
      }
      observe(target: Element) {
        this.callback([{ target, contentRect: { width: 300, height: 480 } } as ResizeObserverEntry], this as unknown as ResizeObserver)
      }
      disconnect() {}
      unobserve() {}
    }
    vi.stubGlobal('ResizeObserver', Observer)
    render(<DiagramObject object={chain} state={null} say="" siblings={1} name="walkthrough" onClose={() => {}} />)
    expect(document.querySelector('[data-diagram-root]')).toHaveAttribute('data-direction', 'TB')
  })

  it('closes from its button', () => {
    const onClose = vi.fn()
    draw(base, onClose)
    fireEvent.click(screen.getByRole('button', { name: 'Close diagram' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('registry', () => {
  it('registers the diagram, visible while shown and drawn in the panel', () => {
    expect(PRIMITIVE_RENDERERS.diagram).toBeDefined()
    expect(hasScenePanel([flow], null)).toBe(true)
    expect(hasScenePanel([flow], { flow: { visible: false } })).toBe(false)
    expect(panelObjects([flow], { flow: { visible: true } }, PRIMITIVE_RENDERERS)).toHaveLength(1)
  })

  it('does not treat a diagram without nodes as drawable', () => {
    expect(hasScenePanel([{ ...flow, params: {} }], null)).toBe(false)
  })
})
