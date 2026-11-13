import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from 'react'
import { CornerDownLeft, Square } from 'lucide-react'
import type { AgentCommand } from '@/types/agent'
import { COMMAND_MENU_ID, CommandMenu, commandOptionId, matchingCommands } from './CommandMenu'

interface PromptLineProps {
  /** Accessible name of the text field. */
  label: string
  placeholder: string
  /** Nothing can be sent at all (no connection, no session, no question). */
  disabled: boolean
  /** The other side has the floor; Stop is offered beside Send. */
  busy?: boolean
  onSend: (text: string) => void | boolean
  onStop?: () => void
  /** Extra controls before Send, such as hold-to-talk. */
  aside?: ReactNode
  /** Context selectors positioned in a quiet row below the input. */
  contextControls?: ReactNode
  /** Dictated text to review: each new id is added to the field, which takes the focus. */
  draft?: { id: number; text: string } | null
  /** What is heard of the words still being spoken: shown muted above the field, never sent. */
  liveTranscript?: string | null
  /** Slash commands to offer while the text is just "/name"; without them there is no menu. */
  commands?: AgentCommand[]
  /**
   * Holding Space in the field is push-to-talk (the `aside` control starts the recording):
   * the text goes back to what it was before the hold, and a single tap still types a space.
   */
  holdSpaceToTalk?: boolean
}

/** The field as it was just before a Space key went down; a hold restores it. */
interface FieldSnapshot {
  value: string
  start: number
  end: number
  restored: boolean
}

/** A command being typed: a slash and name characters, no space or new line yet. */
const COMMAND_QUERY = /^\/(\S*)$/

/** The field grows with its text up to this many pixels, then scrolls (about eight lines). */
const MAX_FIELD_HEIGHT_PX = 200

/** The composer floating near the bottom of the conversation: typing is always one click away. */
export function PromptLine({ label, placeholder, disabled, busy = false, onSend, onStop, aside, contextControls, draft = null, liveTranscript = null, commands, holdSpaceToTalk = false }: PromptLineProps) {
  const [text, setText] = useState('')
  const [seenDraft, setSeenDraft] = useState(0)
  const [active, setActive] = useState(0)
  // The text for which Escape closed the menu; typing on opens it again.
  const [dismissedFor, setDismissedFor] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const spaceSnapshot = useRef<FieldSnapshot | null>(null)
  // A new draft joins what is already typed (adjusting state while rendering, not in an effect).
  if (draft && draft.id !== seenDraft) {
    setSeenDraft(draft.id)
    setText((current) => (current.trim() ? `${current.trimEnd()} ${draft.text}` : draft.text))
  }
  useEffect(() => {
    if (draft) inputRef.current?.focus()
  }, [draft])
  // Long dictation wraps onto more lines instead of scrolling sideways in one row.
  useLayoutEffect(() => {
    const field = inputRef.current
    if (!field) return
    field.style.height = 'auto'
    field.style.height = `${Math.min(field.scrollHeight, MAX_FIELD_HEIGHT_PX)}px`
  }, [text])
  const trimmed = text.trim()
  const canSend = !disabled && !busy && trimmed.length > 0

  const query = COMMAND_QUERY.exec(text)?.[1]
  const matches = query !== undefined && commands?.length && text !== dismissedFor ? matchingCommands(commands, query) : []
  const menuOpen = matches.length > 0
  const highlighted = Math.min(active, matches.length - 1)

  const complete = (command: AgentCommand) => {
    setText(`/${command.name} `)
    setActive(0)
    inputRef.current?.focus()
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!canSend) return
    if (onSend(trimmed) !== false) setText('')
  }

  // Enter sends and Shift+Enter starts a new line, as in a chat; a word still being
  // composed by an input method is never sent.
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (holdSpaceToTalk && event.code === 'Space' && !event.nativeEvent.isComposing) {
      const field = event.currentTarget
      if (!event.repeat) {
        spaceSnapshot.current = { value: field.value, start: field.selectionStart, end: field.selectionEnd, restored: false }
      } else if (spaceSnapshot.current) {
        // The hold has begun: no more spaces, and the one typed by the first press goes away.
        event.preventDefault()
        const snapshot = spaceSnapshot.current
        if (!snapshot.restored) {
          snapshot.restored = true
          setText(snapshot.value)
          field.value = snapshot.value
          field.setSelectionRange(snapshot.start, snapshot.end)
        }
        return
      }
    }
    if (menuOpen && !event.nativeEvent.isComposing) {
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault()
        const step = event.key === 'ArrowDown' ? 1 : -1
        setActive((highlighted + step + matches.length) % matches.length)
        return
      }
      if (event.key === 'Escape') {
        event.preventDefault()
        setDismissedFor(text)
        return
      }
      // A command typed in full is sent as it is; a part of one is completed first.
      const typedInFull = matches.some((command) => command.name === query)
      if (event.key === 'Tab' || (event.key === 'Enter' && !event.shiftKey && !typedInFull)) {
        event.preventDefault()
        complete(matches[highlighted])
        return
      }
    }
    if (event.key !== 'Enter' || event.shiftKey || event.nativeEvent.isComposing) return
    submit(event)
  }

  return (
    <div className="composer-dock">
      <div className="composer-stack">
        {liveTranscript && (
          <p
            data-testid="live-transcript"
            aria-live="polite"
            className="t-ui m-0 px-3 italic"
            style={{ color: 'var(--label-2)' }}
          >
            {liveTranscript}
          </p>
        )}
        <form onSubmit={submit} className="composer">
          {menuOpen && <CommandMenu commands={matches} active={highlighted} onPick={complete} />}
          <textarea
            ref={inputRef}
            rows={1}
            value={text}
            onChange={(event) => {
              setText(event.target.value)
              setActive(0)
            }}
            onKeyDown={onKeyDown}
            onKeyUp={(event) => {
              if (event.code === 'Space') spaceSnapshot.current = null
            }}
            disabled={disabled}
            aria-label={label}
            // Edge's own "Ask Edge to help me write" popup would cover the composer.
            // `writingsuggestions` is not in React's typings yet, but is passed through as is.
            {...{ writingsuggestions: 'false' }}
            aria-controls={menuOpen ? COMMAND_MENU_ID : undefined}
            aria-activedescendant={menuOpen ? commandOptionId(highlighted) : undefined}
            placeholder={placeholder}
            className="t-ui min-h-10 min-w-[8rem] flex-1 resize-none bg-transparent px-2.5 py-2 outline-none placeholder:text-[var(--label-2)] disabled:opacity-60"
            style={{ color: 'var(--label)', maxHeight: MAX_FIELD_HEIGHT_PX }}
          />
          <div className="flex shrink-0 items-center gap-2">
            {aside}
            {busy && onStop && (
              <button type="button" onClick={onStop} aria-label="Stop" title="Stop (interrupts the reply)" className="key" data-shape="square" data-tone="danger">
                <Square aria-hidden="true" className="h-3.5 w-3.5" fill="currentColor" strokeWidth={0} />
              </button>
            )}
            <button type="submit" aria-label="Send" title="Send (Enter)" disabled={!canSend} className="key" data-shape="square" data-tone="primary">
              <CornerDownLeft aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
            </button>
          </div>
        </form>
        {contextControls}
      </div>
    </div>
  )
}
