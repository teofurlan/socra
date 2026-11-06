import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PRIMITIVE_RENDERERS, hasScenePanel, type PrimitiveRenderers } from '@/components/scene/registry'
import { SceneStack } from '@/components/scene/SceneStack'
import type { WalkthroughData } from '@/types/exam'

const CODE = 'one\ntwo\nthree'

function scene(objects: WalkthroughData['objects'], state: Record<string, Record<string, unknown> & { visible: boolean }>, say = 'The middle one.'): WalkthroughData {
  return { title: 'T', objects, total: 1, step: { index: 1, total: 1, id: 's1', say, state }, status: 'playing', reason: null }
}
const code = { id: 'code', primitive: 'code', params: { code: CODE, language: 'python' }, hidden: false }

describe('SceneStack', () => {
  it('draws a code object through the registry with its line focus', () => {
    render(<SceneStack walkthrough={scene([code], { code: { visible: true, lines: [2, 2] } })} onClose={() => {}} />)
    expect(screen.getByRole('region', { name: 'Walkthrough code' })).toBeInTheDocument()
    const focused = document.querySelectorAll('pre[data-scene-object="code"] [data-focused="true"]')
    expect(focused).toHaveLength(1)
    expect(focused[0]).toHaveTextContent('two')
  })

  it('shows the step text for a primitive it does not know, without throwing', () => {
    const unknown = { id: 'd', primitive: 'hologram', params: {}, hidden: false }
    render(<SceneStack walkthrough={scene([unknown], { d: { visible: true } }, 'Arrows between boxes.')} onClose={() => {}} />)
    expect(screen.getByTestId('scene-fallback')).toHaveTextContent('Arrows between boxes.')
  })

  it('shows the step text when a primitive fails to render, and keeps the others', () => {
    const boom = { id: 'b', primitive: 'boom', params: {}, hidden: false }
    const renderers: PrimitiveRenderers = {
      boom: { visible: () => true, Component: () => { throw new Error('render failed') } },
    }
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(<SceneStack renderers={{ ...PRIMITIVE_RENDERERS, ...renderers }} walkthrough={scene([boom, code], { b: { visible: true }, code: { visible: true, lines: [1, 1] } }, 'Still talking.')} onClose={() => {}} />)
    error.mockRestore()
    expect(screen.getByTestId('scene-fallback')).toHaveTextContent('Still talking.')
    expect(screen.getByRole('region', { name: /Walkthrough code/ })).toBeInTheDocument()
  })

  it('recovers when the next step renders fine', () => {
    const flaky: PrimitiveRenderers = {
      flaky: { visible: () => true, Component: ({ state }) => { if (state?.bad) throw new Error('bad'); return <p>fine</p> } },
    }
    const object = { id: 'f', primitive: 'flaky', params: {}, hidden: false }
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { rerender } = render(<SceneStack renderers={flaky} walkthrough={scene([object], { f: { visible: true, bad: true } })} onClose={() => {}} />)
    expect(screen.getByTestId('scene-fallback')).toBeInTheDocument()
    rerender(<SceneStack renderers={flaky} walkthrough={{ ...scene([object], { f: { visible: true } }), step: { index: 2, total: 2, id: 's2', say: 'ok', state: { f: { visible: true } } } }} onClose={() => {}} />)
    error.mockRestore()
    expect(screen.queryByTestId('scene-fallback')).not.toBeInTheDocument()
    expect(screen.getByText('fine')).toBeInTheDocument()
  })
})

describe('hasScenePanel', () => {
  it('is true for visible code and unknown primitives, false for particle-only ones', () => {
    const headline = { id: 'h', primitive: 'headline', params: { text: 'Hi' }, hidden: false }
    const shape = { id: 's', primitive: 'shape', params: { shape: 'cube' }, hidden: false }
    expect(hasScenePanel([headline, shape], null)).toBe(false)
    expect(hasScenePanel([headline, code], null)).toBe(true)
    expect(hasScenePanel([{ id: 'd', primitive: 'hologram', params: {}, hidden: false }], null)).toBe(true)
  })

  it('follows the step state: hidden objects take no panel', () => {
    expect(hasScenePanel([code], { code: { visible: false } })).toBe(false)
    expect(hasScenePanel([{ ...code, hidden: true }], null)).toBe(false)
  })
})
