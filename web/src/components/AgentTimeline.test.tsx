import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { AgentTimeline } from './AgentTimeline'
import type { TimelineEntry } from '@/types/agent'

const entries: TimelineEntry[] = [
  { id: 1, kind: 'user', text: 'explain' },
  { id: 2, kind: 'reply', text: 'Intro line.\n\n- First **point** here.\n- Second point.' },
]

class FakeHighlight {
  ranges: Range[]
  constructor(...ranges: Range[]) {
    this.ranges = ranges
  }
}

describe('AgentTimeline spoken highlight', () => {
  afterEach(() => vi.unstubAllGlobals())

  const withHighlightApi = () => {
    const registry = new Map<string, FakeHighlight>()
    vi.stubGlobal('Highlight', FakeHighlight)
    vi.stubGlobal('CSS', { highlights: registry })
    return registry
  }

  it('does not crash and highlights nothing when the API is missing', () => {
    render(<AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 1, text: 'Intro line.' }} />)

    expect(screen.getByText('Intro line.')).toBeInTheDocument()
  })

  it('highlights the playing clip over the rendered text, leaving the markup alone', () => {
    const registry = withHighlightApi()
    const { container } = render(
      <AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 1, text: '- First **point** here.' }} />,
    )
    const before = container.innerHTML

    const range = registry.get('socra-spoken')?.ranges[0]
    expect(range?.toString()).toBe('First point here.')
    expect(container.innerHTML).toBe(before)
    expect(container.querySelector('strong')?.textContent).toBe('point')
  })

  it('follows the next clip and clears when nothing is spoken', () => {
    const registry = withHighlightApi()
    const { rerender } = render(<AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 1, text: 'Intro line.' }} />)
    expect(registry.get('socra-spoken')?.ranges[0].toString()).toBe('Intro line.')

    rerender(<AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 2, text: 'Second point.' }} />)
    expect(registry.get('socra-spoken')?.ranges[0].toString()).toBe('Second point.')

    rerender(<AgentTimeline entries={entries} protocolState="listening" spoken={null} />)
    expect(registry.has('socra-spoken')).toBe(false)
  })

  it('highlights nothing when the clip text is not on screen', () => {
    const registry = withHighlightApi()
    render(<AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 1, text: 'Something unrelated.' }} />)

    expect(registry.has('socra-spoken')).toBe(false)
  })

  it('removes the highlight when the timeline unmounts', () => {
    const registry = withHighlightApi()
    const { unmount } = render(<AgentTimeline entries={entries} protocolState="speaking" spoken={{ id: 1, text: 'Intro line.' }} />)
    unmount()

    expect(registry.has('socra-spoken')).toBe(false)
  })
})

describe('AgentTimeline teleprompter', () => {
  const rect = (top: number, height: number) => ({ top, height, bottom: top + height, left: 0, right: 0, width: 0, x: 0, y: top, toJSON: () => ({}) })
  let frames: Array<() => void>
  let scrollIntoView: ReturnType<typeof vi.fn>
  let scrollTo: ReturnType<typeof vi.fn>

  beforeEach(() => {
    frames = []
    vi.stubGlobal('requestAnimationFrame', (cb: () => void) => frames.push(cb))
    vi.stubGlobal('cancelAnimationFrame', () => {})
    scrollIntoView = vi.fn()
    scrollTo = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView as unknown as typeof Element.prototype.scrollIntoView
    Element.prototype.scrollTo = scrollTo as unknown as typeof Element.prototype.scrollTo
    ;(Range.prototype as unknown as { getBoundingClientRect: () => DOMRect }).getBoundingClientRect = () => rect(400, 20) as DOMRect
    const registry = new Map<string, FakeHighlight>()
    vi.stubGlobal('Highlight', FakeHighlight)
    vi.stubGlobal('CSS', { highlights: registry })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    delete (Element.prototype as { scrollIntoView?: unknown }).scrollIntoView
    delete (Element.prototype as { scrollTo?: unknown }).scrollTo
    delete (Range.prototype as { getBoundingClientRect?: unknown }).getBoundingClientRect
  })

  const flush = () => { const run = frames; frames = []; run.forEach((f) => f()) }

  const mount = (spoken: { id: number; text: string } | null, list: TimelineEntry[] = entries) => {
    const view = render(
      <div className="shell-scroll" data-testid="scroller">
        <AgentTimeline entries={list} protocolState="speaking" spoken={spoken} />
      </div>,
    )
    const scroller = view.getByTestId('scroller')
    scroller.getBoundingClientRect = () => rect(100, 400) as DOMRect
    Object.defineProperty(scroller, 'clientHeight', { configurable: true, value: 400 })
    scroller.scrollTop = 50
    const update = (next: { id: number; text: string } | null, nextList: TimelineEntry[] = list) =>
      view.rerender(
        <div className="shell-scroll" data-testid="scroller">
          <AgentTimeline entries={nextList} protocolState="speaking" spoken={next} />
        </div>,
      )
    return { ...view, scroller, update }
  }

  it('centers the highlighted range in the scroll area, smoothly', () => {  // S6
    const { update } = mount(null)
    update({ id: 1, text: 'Intro line.' })

    expect(scrollTo).toHaveBeenLastCalledWith({ top: 160, behavior: 'smooth' })
  })

  it('re-centers on each new clip', () => {  // S6
    const { update } = mount(null)
    update({ id: 1, text: 'Intro line.' })
    update({ id: 2, text: 'Second point.' })

    expect(scrollTo).toHaveBeenCalledTimes(2)
  })

  it('scrolls instantly with reduced motion', () => {  // S6
    vi.stubGlobal('matchMedia', (query: string) => ({ matches: query.includes('reduce') }))
    const { update } = mount(null)
    update({ id: 1, text: 'Intro line.' })

    expect(scrollTo).toHaveBeenLastCalledWith({ top: 160, behavior: 'auto' })
  })

  it('adds bottom space of half the scroller while speaking and keeps it when speech ends', () => {  // S7
    const { update } = mount(null)
    expect(screen.getByTestId('speech-spacer').style.height).toBe('0px')

    update({ id: 1, text: 'Intro line.' })
    expect(screen.getByTestId('speech-spacer').style.height).toBe('200px')

    update(null)
    expect(screen.getByTestId('speech-spacer').style.height).toBe('200px')
  })

  it('drops the bottom space at the next user turn', () => {  // S7
    const { update } = mount(null)
    update({ id: 1, text: 'Intro line.' })
    update(null, [...entries, { id: 3, kind: 'user', text: 'and then?' }])

    expect(screen.getByTestId('speech-spacer').style.height).toBe('0px')
  })

  it('does not follow the newest entry while a clip is highlighted, and resumes after', () => {  // S8
    const { update } = mount(null)
    flush()
    scrollIntoView.mockClear()

    update({ id: 1, text: 'Intro line.' })
    update({ id: 1, text: 'Intro line.' }, [...entries, { id: 3, kind: 'text', text: 'More.' }])
    flush()
    expect(scrollIntoView).not.toHaveBeenCalled()

    update(null, [...entries, { id: 3, kind: 'text', text: 'More.' }, { id: 4, kind: 'user', text: 'ok' }])
    flush()
    expect(scrollIntoView).toHaveBeenCalled()
  })

  it('does not center or crash without a match or the highlight API', () => {  // S9
    const { update } = mount(null)
    update({ id: 1, text: 'Something unrelated.' })
    expect(scrollTo).not.toHaveBeenCalled()

    vi.stubGlobal('CSS', {})
    update({ id: 2, text: 'Intro line.' })
    expect(scrollTo).not.toHaveBeenCalled()
  })
})
