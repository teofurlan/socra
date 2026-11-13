import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PromptLine } from './PromptLine'

function setup(draft: { id: number; text: string } | null = null) {
  const onSend = vi.fn()
  const view = render(<PromptLine label="Message Socra" placeholder="Say it" disabled={false} onSend={onSend} draft={draft} />)
  const rerender = (next: { id: number; text: string } | null) =>
    view.rerender(<PromptLine label="Message Socra" placeholder="Say it" disabled={false} onSend={onSend} draft={next} />)
  return { onSend, rerender, input: () => screen.getByLabelText('Message Socra') as HTMLInputElement }
}

describe('PromptLine dictation draft', () => {
  it('puts a draft in the field, focuses it, and sends the edited text with Enter', async () => {
    const user = userEvent.setup()
    const { onSend, rerender, input } = setup()

    rerender({ id: 1, text: 'fix the build' })

    expect(input()).toHaveValue('fix the build')
    expect(input()).toHaveFocus()
    await user.type(input(), ' please{Enter}')
    expect(onSend).toHaveBeenCalledWith('fix the build please')
    expect(input()).toHaveValue('')
  })

  it('adds a new draft after what is already typed, and leaves edits alone when the same draft renders again', async () => {
    const user = userEvent.setup()
    const { rerender, input } = setup()
    await user.type(input(), 'first')

    rerender({ id: 1, text: 'second' })
    expect(input()).toHaveValue('first second')

    await user.type(input(), '!')
    rerender({ id: 1, text: 'second' })
    expect(input()).toHaveValue('first second!')

    rerender({ id: 2, text: 'third' })
    expect(input()).toHaveValue('first second! third')
  })

  it('shows nothing extra when there is no draft', () => {
    const { input } = setup(null)
    expect(input()).toHaveValue('')
  })
})

describe('PromptLine live transcript', () => {
  const renderLive = (liveTranscript: string | null) =>
    render(<PromptLine label="Message Socra" placeholder="Say it" disabled={false} onSend={vi.fn()} liveTranscript={liveTranscript} />)

  it('shows the provisional text beside the field, announced politely, without touching the field', () => {
    renderLive('list the files in')

    expect(screen.getByTestId('live-transcript')).toHaveTextContent('list the files in')
    expect(screen.getByTestId('live-transcript')).toHaveAttribute('aria-live', 'polite')
    expect(screen.getByLabelText('Message Socra')).toHaveValue('')
  })

  it('shows nothing without a provisional transcript', () => {
    renderLive(null)

    expect(screen.queryByTestId('live-transcript')).not.toBeInTheDocument()
  })

  it('never sends the provisional text', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<PromptLine label="Message Socra" placeholder="Say it" disabled={false} onSend={onSend} liveTranscript="hello there" />)

    await user.click(screen.getByLabelText('Message Socra'))
    await user.keyboard('{Enter}')

    expect(onSend).not.toHaveBeenCalled()
  })
})

describe('PromptLine grows with long text', () => {
  it('is a multi-line field: Shift+Enter starts a new line and Enter sends everything', async () => {
    const user = userEvent.setup()
    const { onSend, input } = setup()

    expect(input()).toBeInstanceOf(HTMLTextAreaElement)
    await user.type(input(), 'first line{Shift>}{Enter}{/Shift}second line')
    expect(onSend).not.toHaveBeenCalled()
    expect(input()).toHaveValue('first line\nsecond line')

    await user.keyboard('{Enter}')
    expect(onSend).toHaveBeenCalledWith('first line\nsecond line')
    expect(input()).toHaveValue('')
  })

  it('does not send while an input method is still composing a word', async () => {
    const { onSend, input } = setup()
    const { fireEvent } = await import('@testing-library/react')

    fireEvent.change(input(), { target: { value: 'hola' } })
    fireEvent.keyDown(input(), { key: 'Enter', isComposing: true })

    expect(onSend).not.toHaveBeenCalled()
  })
})
