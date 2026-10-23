import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { CodePane } from './CodePane'

describe('CodePane', () => {
  it('shows display-only code verbatim with line numbers outside the text', () => {
    const code = 'const value = "<script>";\n  return value'
    const { container } = render(<CodePane code={code} name="ts" label="Code" onClose={vi.fn()} />)

    const region = screen.getByRole('region', { name: 'Code' })
    const lines = Array.from(region.querySelectorAll('code > span')).map((line) => line.lastChild?.textContent)
    expect(lines).toEqual(['const value = "<script>";', '  return value'])
    expect(container.querySelector('script')).not.toBeInTheDocument()
    expect(region).toHaveTextContent('2 lines')
  })

  it('colours the code by syntax at reading size', () => {
    render(<CodePane code={'const delay = 500 // ms'} name="ts" label="Code" onClose={vi.fn()} />)
    const pre = screen.getByRole('region', { name: 'Code' }).querySelector('pre')!
    expect(pre).toHaveClass('t-code')
    const token = (kind: string) => Array.from(pre.querySelectorAll(`[data-token="${kind}"]`)).map((t) => t.textContent)
    expect(token('keyword')).toEqual(['const'])
    expect(token('number')).toEqual(['500'])
    expect(token('comment')).toEqual(['// ms'])
  })

  it('scrolls long code inside a focusable block and closes on request', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(<CodePane code={'x'.repeat(500)} name="question 1" label="Question code" onClose={onClose} />)

    const pre = screen.getByRole('region', { name: 'Question code' }).querySelector('pre')!
    expect(pre).toHaveClass('overflow-auto')
    expect(pre).toHaveAttribute('tabindex', '0')

    await user.click(screen.getByRole('button', { name: 'Close code' }))
    expect(onClose).toHaveBeenCalled()
  })
})

describe('CodePane focus', () => {
  const code = 'one\ntwo\nthree\nfour'

  it('marks only the focused lines', () => {
    render(<CodePane code={code} name="ts" label="Code" focus={[2, 3]} onClose={vi.fn()} />)
    const lines = Array.from(screen.getByRole('region', { name: 'Code' }).querySelectorAll('code > span'))
    expect(lines.map((line) => line.hasAttribute('data-focused'))).toEqual([false, true, true, false])
  })

  it('marks nothing without a focus', () => {
    render(<CodePane code={code} name="ts" label="Code" focus={null} onClose={vi.fn()} />)
    expect(document.querySelector('[data-focused]')).toBeNull()
  })

  it('scrolls the first focused line into view when the focus changes', () => {
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const { rerender } = render(<CodePane code={code} name="ts" label="Code" focus={[1, 1]} onClose={vi.fn()} />)
    scrollIntoView.mockClear()
    rerender(<CodePane code={code} name="ts" label="Code" focus={[3, 4]} onClose={vi.fn()} />)
    expect(scrollIntoView).toHaveBeenCalledTimes(1)
    expect(scrollIntoView.mock.contexts[0]).toBe(document.querySelectorAll('code > span')[2])
  })
})
