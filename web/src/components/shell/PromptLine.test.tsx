import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PromptLine } from './PromptLine'
import type { AgentCommand } from '@/types/agent'

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

describe('PromptLine slash commands', () => {
  const commands: AgentCommand[] = [
    { name: 'tdd', description: 'Test-driven development', hint: '<feature>' },
    { name: 'context', description: 'Show context usage', hint: '' },
    { name: 'code-review', description: 'Review the changes', hint: '' },
    { name: 'skill:grilling', description: 'Grill the plan', hint: '' },
  ]

  function setupMenu(list: AgentCommand[] | null = commands) {
    const onSend = vi.fn()
    render(<PromptLine label="Message Socra" placeholder="Say it" disabled={false} onSend={onSend} commands={list ?? undefined} />)
    return { onSend, input: () => screen.getByLabelText('Message Socra') as HTMLTextAreaElement }
  }
  const options = () =>
    screen.queryAllByRole('option').map((option) => option.querySelector('[data-command-name]')?.textContent ?? '')

  it('lists every command with its description and argument hint when the text is just a slash', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()

    await user.type(input(), '/')

    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(options()).toHaveLength(4)
    const tdd = screen.getByRole('option', { name: /tdd/ })
    expect(tdd).toHaveTextContent('/tdd')
    expect(tdd).toHaveTextContent('<feature>')
    expect(tdd).toHaveTextContent('Test-driven development')
  })

  it('filters as the user types, names that start with it first', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()

    await user.type(input(), '/co')

    expect(options()).toEqual(['/context', '/code-review'])
    await user.clear(input())
    await user.type(input(), '/grill')
    // A name that merely contains the text still matches, after the ones that start with it.
    expect(options()).toEqual(['/skill:grilling'])
  })

  it('shows no menu for ordinary text, without commands, or when nothing matches', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()
    await user.type(input(), 'hello /')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    await user.clear(input())
    await user.type(input(), '/zzz')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('shows no menu at all on a page that passes no commands', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu(null)

    await user.type(input(), '/')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('moves with the arrow keys and completes the highlighted command with Tab', async () => {
    const user = userEvent.setup()
    const { input, onSend } = setupMenu()
    await user.type(input(), '/co')

    await user.keyboard('{ArrowDown}')
    expect(screen.getByRole('option', { selected: true })).toHaveTextContent('/code-review')
    expect(input()).toHaveAttribute('aria-activedescendant', screen.getByRole('option', { selected: true }).id)
    await user.keyboard('{Tab}')

    expect(input()).toHaveValue('/code-review ')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(onSend).not.toHaveBeenCalled()
  })

  it('ArrowUp wraps to the last match', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()
    await user.type(input(), '/')

    await user.keyboard('{ArrowUp}')

    expect(screen.getByRole('option', { selected: true })).toHaveTextContent('/skill:grilling')
    expect(input()).toHaveFocus()
  })

  it('Enter on a partly typed command completes it instead of sending', async () => {
    const user = userEvent.setup()
    const { input, onSend } = setupMenu()
    await user.type(input(), '/td{Enter}')

    expect(input()).toHaveValue('/tdd ')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('Enter on a fully typed command sends it', async () => {
    const user = userEvent.setup()
    const { input, onSend } = setupMenu()

    await user.type(input(), '/tdd{Enter}')

    expect(onSend).toHaveBeenCalledWith('/tdd')
    expect(input()).toHaveValue('')
  })

  it('the argument typed after a completed command is sent with Enter', async () => {
    const user = userEvent.setup()
    const { input, onSend } = setupMenu()

    await user.type(input(), '/td{Tab}fix the login{Enter}')

    expect(onSend).toHaveBeenCalledWith('/tdd fix the login')
  })

  it('Escape closes the menu and keeps the text; typing on opens it again', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()
    await user.type(input(), '/c')

    await user.keyboard('{Escape}')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(input()).toHaveValue('/c')

    await user.type(input(), 'o')
    expect(screen.getByRole('listbox')).toBeInTheDocument()
  })

  it('Shift+Enter still starts a new line and a word being composed is never completed', async () => {
    const user = userEvent.setup()
    const { input, onSend } = setupMenu()
    await user.type(input(), '/td')

    fireEvent.keyDown(input(), { key: 'Enter', isComposing: true })
    expect(input()).toHaveValue('/td')

    await user.type(input(), 'd arg{Shift>}{Enter}{/Shift}more')
    expect(input()).toHaveValue('/tdd arg\nmore')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('clicking a command completes it and keeps the field focused', async () => {
    const user = userEvent.setup()
    const { input } = setupMenu()
    await user.type(input(), '/')

    await user.click(screen.getByRole('option', { name: /context/ }))

    expect(input()).toHaveValue('/context ')
    expect(input()).toHaveFocus()
  })
})
