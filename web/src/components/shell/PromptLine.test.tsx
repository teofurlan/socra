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
