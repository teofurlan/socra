import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { CornerDownLeft, Square } from 'lucide-react'

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
}

/** The composer floating near the bottom of the conversation: typing is always one click away. */
export function PromptLine({ label, placeholder, disabled, busy = false, onSend, onStop, aside, contextControls, draft = null, liveTranscript = null }: PromptLineProps) {
  const [text, setText] = useState('')
  const [seenDraft, setSeenDraft] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  // A new draft joins what is already typed (adjusting state while rendering, not in an effect).
  if (draft && draft.id !== seenDraft) {
    setSeenDraft(draft.id)
    setText((current) => (current.trim() ? `${current.trimEnd()} ${draft.text}` : draft.text))
  }
  useEffect(() => {
    if (draft) inputRef.current?.focus()
  }, [draft])
  const trimmed = text.trim()
  const canSend = !disabled && !busy && trimmed.length > 0

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (!canSend) return
    if (onSend(trimmed) !== false) setText('')
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
          <input
            ref={inputRef}
            type="text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            disabled={disabled}
            aria-label={label}
            placeholder={placeholder}
            className="t-ui min-h-10 min-w-[8rem] flex-1 bg-transparent px-2.5 outline-none placeholder:text-[var(--label-2)] disabled:opacity-60"
            style={{ color: 'var(--label)' }}
          />
          <div className="flex shrink-0 items-center gap-2">
            {aside}
            {busy && onStop && (
              <button type="button" onClick={onStop} aria-label="Stop" title="Stop (interrupts the reply)" className="key min-h-10" data-tone="danger">
                <Square aria-hidden="true" className="h-3 w-3" fill="currentColor" strokeWidth={0} />
                Stop
              </button>
            )}
            <button type="submit" aria-label="Send" disabled={!canSend} className="key min-h-10" data-tone="primary">
              <CornerDownLeft aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={2} />
              Send
            </button>
          </div>
        </form>
        {contextControls}
      </div>
    </div>
  )
}
