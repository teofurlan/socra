import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentTimeline } from './AgentTimeline'
import { PushToTalkControl } from './PushToTalkControl'
import { PermissionPromptCard } from './PermissionPromptCard'
import { PromptLine } from './shell/PromptLine'
import type { TimelineEntry } from '@/types/agent'

describe('AgentTimeline', () => {
  it('shows each kind of entry in order', () => {
    const entries: TimelineEntry[] = [
      { id: 1, kind: 'user', text: 'what is here?' },
      { id: 2, kind: 'text', text: 'Let me look.' },
      { id: 3, kind: 'tool', text: 'src/app.py', tool: 'Read' },
      { id: 4, kind: 'reply', text: 'An exam app.' },
      { id: 5, kind: 'error', text: 'Rate limited' },
    ]
    render(<AgentTimeline entries={entries} protocolState="listening" />)

    const items = screen.getAllByRole('listitem')
    expect(items.map((item) => item.dataset.kind)).toEqual(['user', 'text', 'tool', 'reply', 'error'])
    expect(items[2]).toHaveTextContent('Read')
    expect(items[2]).toHaveTextContent('src/app.py')
    expect(items[4]).toHaveTextContent('Rate limited')
  })

  it('marks where the context was condensed without a speaker label', () => {
    const entries: TimelineEntry[] = [
      { id: 1, kind: 'reply', text: 'Login added.' },
      { id: 2, kind: 'handoff', text: 'Context condensed · Exam' },
      { id: 3, kind: 'reply', text: 'Shall I quiz you?' },
    ]
    render(<AgentTimeline entries={entries} protocolState="listening" />)

    const items = screen.getAllByRole('listitem')
    expect(items.map((item) => item.dataset.kind)).toEqual(['reply', 'handoff', 'reply'])
    expect(items[1]).toHaveTextContent('Context condensed · Exam')
    expect(items[1].textContent).not.toMatch(/socra|you/)
  })

  it('shows inline code and tool paths in mono, without the backticks', () => {
    const entries: TimelineEntry[] = [
      { id: 1, kind: 'tool', text: 'web/src/lib/retry.ts', tool: 'Read' },
      { id: 2, kind: 'reply', text: 'Apply it to `web/src/lib/retry.ts` now?' },
    ]
    render(<AgentTimeline entries={entries} protocolState="speaking" />)

    const items = screen.getAllByRole('listitem')
    expect(items[0].querySelector('.t-mono')).toHaveTextContent('web/src/lib/retry.ts')
    const code = items[1].querySelector('code')
    expect(code).toHaveTextContent('web/src/lib/retry.ts')
    expect(items[1]).toHaveTextContent('Apply it to web/src/lib/retry.ts now?')
    expect(items[1].textContent).not.toContain('`')
  })

  it('renders the supported Markdown subset in replies and user messages', () => {
    const entries: TimelineEntry[] = [
      { id: 1, kind: 'user', text: '**My request** with *context*.' },
      {
        id: 2,
        kind: 'reply',
        text: '## Summary\n\n**Bold** and *italic* with [docs](https://example.com) and `code`.\n\n- first\n- second\n\n> quoted',
      },
    ]
    render(<AgentTimeline entries={entries} protocolState="speaking" />)

    const items = screen.getAllByRole('listitem')
    expect(items[0].querySelector('strong')).toHaveTextContent('My request')
    expect(items[0].querySelector('em')).toHaveTextContent('context')
    expect(items[1].querySelector('h2')).toHaveTextContent('Summary')
    expect(items[1].querySelector('strong')).toHaveTextContent('Bold')
    expect(items[1].querySelector('em')).toHaveTextContent('italic')
    expect(items[1].querySelector('code')).toHaveTextContent('code')
    expect(items[1].querySelectorAll('li')).toHaveLength(2)
    expect(items[1].querySelector('blockquote')).toHaveTextContent('quoted')
    const link = items[1].querySelector('a')
    expect(link).toHaveAttribute('href', 'https://example.com')
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('keeps raw HTML and unsafe links as plain text', () => {
    const reply = '<img src=x onerror=alert(1)> [bad](javascript:alert(1))'
    render(<AgentTimeline entries={[{ id: 1, kind: 'reply', text: reply }]} protocolState="speaking" />)

    const item = screen.getByRole('listitem')
    expect(item.querySelector('img')).not.toBeInTheDocument()
    expect(item.querySelector('a')).not.toBeInTheDocument()
    expect(item).toHaveTextContent(reply)
  })

  it('points to the code panel where the code was, between the paragraphs around it', () => {
    const reply = 'Cap the delay instead:\n\n```ts\nconst a = 1\nconst b = 2\n```\n\nWant me to apply it?'
    render(<AgentTimeline entries={[{ id: 1, kind: 'reply', text: reply }]} protocolState="speaking" />)

    const text = screen.getByRole('listitem').textContent ?? ''
    const pointer = screen.getByTestId('code-pointer')
    expect(pointer).toHaveTextContent('code panel · ts · 2 lines')
    expect(text.indexOf('instead:')).toBeLessThan(text.indexOf('code panel'))
    expect(text.indexOf('code panel')).toBeLessThan(text.indexOf('Want me'))
    expect(text).not.toContain('const a')
    expect(screen.getAllByTestId('code-pointer')).toHaveLength(1)
  })

  it('stays at the newest entry when the conversation is resized', () => {
    let onResize = () => {}
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(cb: () => void) {
          onResize = cb
        }
        observe() {}
        disconnect() {}
      },
    )
    const scrolled = vi.fn()
    Element.prototype.scrollIntoView = scrolled
    // The page opens with an empty conversation; the first reply arrives later.
    const { rerender } = render(
      <div className="shell-scroll">
        <AgentTimeline entries={[]} protocolState="idle" />
      </div>,
    )
    rerender(
      <div className="shell-scroll">
        <AgentTimeline entries={[{ id: 1, kind: 'reply', text: 'Done.' }]} protocolState="idle" />
      </div>,
    )
    scrolled.mockClear()
    onResize()
    expect(scrolled).toHaveBeenCalledWith({ block: 'end' })
    vi.unstubAllGlobals()
  })

  it('invites the first turn when empty', () => {
    render(<AgentTimeline entries={[]} protocolState="listening" />)

    expect(screen.getByTestId('timeline-empty')).toHaveTextContent(/speak or type/i)
  })
})

describe('PermissionPromptCard', () => {
  const prompts = [
    { id: 'r1', tool: 'Bash', title: 'Run git status', detail: 'git status' },
    { id: 'r2', tool: 'Write', title: 'Write a file', detail: 'a.txt' },
  ]

  it('asks about the oldest request and answers it', async () => {
    const user = userEvent.setup()
    const onAnswer = vi.fn()
    render(<PermissionPromptCard prompts={prompts} onAnswer={onAnswer} />)

    const card = screen.getByRole('group', { name: /run git status/i })
    expect(card).toHaveTextContent('git status')
    expect(card).toHaveTextContent('1 more waiting')

    await user.click(screen.getByRole('button', { name: 'Allow' }))
    await user.click(screen.getByRole('button', { name: 'Deny' }))

    expect(onAnswer).toHaveBeenNthCalledWith(1, 'r1', true)
    expect(onAnswer).toHaveBeenNthCalledWith(2, 'r1', false)
  })

  it('renders nothing without pending requests', () => {
    const { container } = render(<PermissionPromptCard prompts={[]} onAnswer={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })
})

describe('PromptLine', () => {
  it('sends a typed turn and clears the field', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()
    render(<PromptLine label="Message Socra" placeholder="Type" disabled={false} busy={false} onSend={onSend} onStop={vi.fn()} />)

    const field = screen.getByLabelText('Message Socra')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    await user.type(field, '  list the files  {Enter}')

    expect(onSend).toHaveBeenCalledWith('list the files')
    expect(field).toHaveValue('')
  })

  it('offers Stop while the agent works and blocks sending', async () => {
    const user = userEvent.setup()
    const onStop = vi.fn()
    render(<PromptLine label="Message Socra" placeholder="Type" disabled={false} busy onSend={vi.fn()} onStop={onStop} />)

    await user.type(screen.getByLabelText('Message Socra'), 'more')
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(onStop).toHaveBeenCalled()
  })

  it('has no Stop button when idle', () => {
    render(<PromptLine label="Message Socra" placeholder="Type" disabled={false} busy={false} onSend={vi.fn()} onStop={vi.fn()} />)

    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull()
  })

  it('shows Send and Stop as square icon-only buttons that keep their accessible names', () => {
    render(<PromptLine label="Message Socra" placeholder="Type" disabled={false} busy onSend={vi.fn()} onStop={vi.fn()} />)

    for (const name of ['Send', 'Stop']) {
      const button = screen.getByRole('button', { name })
      expect(button).toHaveAttribute('data-shape', 'square')
      expect(button.textContent).toBe('')
      expect(button.querySelector('svg')).not.toBeNull()
    }
  })

  describe('holding Space to talk', () => {
    // jsdom neither types the space nor auto-repeats, so both are simulated.
    const typeSpace = (field: HTMLElement, value: string) => {
      fireEvent.keyDown(field, { code: 'Space', key: ' ' })
      fireEvent.change(field, { target: { value } })
    }
    const setup = (holdSpaceToTalk: boolean) => {
      const onTalkingChange = vi.fn()
      render(
        <PromptLine
          label="Message Socra"
          placeholder="Type"
          disabled={false}
          onSend={vi.fn()}
          holdSpaceToTalk={holdSpaceToTalk}
          aside={<PushToTalkControl onTalkingChange={onTalkingChange} />}
        />,
      )
      const field = screen.getByLabelText('Message Socra') as HTMLTextAreaElement
      fireEvent.change(field, { target: { value: 'hello' } })
      field.setSelectionRange(5, 5)
      return { field, onTalkingChange }
    }

    it('keeps a single tap as one typed space', () => {
      const { field, onTalkingChange } = setup(true)
      typeSpace(field, 'hello ')
      fireEvent.keyUp(field, { code: 'Space' })

      expect(field).toHaveValue('hello ')
      expect(onTalkingChange).not.toHaveBeenCalled()
    })

    it('starts push-to-talk on a hold and restores the text and caret from before it', () => {
      const { field, onTalkingChange } = setup(true)
      typeSpace(field, 'hello ')
      expect(fireEvent.keyDown(field, { code: 'Space', key: ' ', repeat: true })).toBe(false)
      fireEvent.keyDown(field, { code: 'Space', key: ' ', repeat: true })

      expect(field).toHaveValue('hello')
      expect(field.selectionStart).toBe(5)
      expect(field.selectionEnd).toBe(5)
      expect(onTalkingChange.mock.calls).toEqual([[true]])

      fireEvent.keyUp(field, { code: 'Space' })
      expect(onTalkingChange.mock.calls).toEqual([[true], [false]])
      expect(field).toHaveValue('hello')
    })

    it('restores a caret in the middle of the text', () => {
      const { field } = setup(true)
      field.setSelectionRange(2, 2)
      typeSpace(field, 'he llo')
      fireEvent.keyDown(field, { code: 'Space', key: ' ', repeat: true })

      expect(field).toHaveValue('hello')
      expect(field.selectionStart).toBe(2)
    })

    it('types a space again after a hold has ended', () => {
      const { field } = setup(true)
      typeSpace(field, 'hello ')
      fireEvent.keyDown(field, { code: 'Space', key: ' ', repeat: true })
      fireEvent.keyUp(field, { code: 'Space' })
      typeSpace(field, 'hello ')

      expect(field).toHaveValue('hello ')
    })

    it('leaves the text alone when holding Space is not for talking', () => {
      const { field } = setup(false)
      typeSpace(field, 'hello ')
      fireEvent.keyDown(field, { code: 'Space', key: ' ', repeat: true })
      fireEvent.change(field, { target: { value: 'hello  ' } })

      expect(field).toHaveValue('hello  ')
    })
  })

  it("opts the field out of the browser's writing suggestions (Edge Compose)", () => {
    render(<PromptLine label="Message Socra" placeholder="Type" disabled={false} onSend={vi.fn()} />)

    expect(screen.getByRole('textbox', { name: 'Message Socra' })).toHaveAttribute('writingsuggestions', 'false')
  })
})
