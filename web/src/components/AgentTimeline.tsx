import { useEffect, useRef } from 'react'
import { codeSegments } from '@/lib/codeBlocks'
import type { ProtocolState } from '@/types/exam'
import type { TimelineEntry } from '@/types/agent'
import { MarkdownText } from './MarkdownText'

interface AgentTimelineProps {
  entries: TimelineEntry[]
  protocolState: ProtocolState
}

/** Who said it, in the left column of the log, like a shell prompt. */
const WHO: Record<TimelineEntry['kind'], { label: string; color: string }> = {
  user: { label: 'you', color: 'var(--live)' },
  text: { label: 'socra', color: 'var(--label-3)' },
  tool: { label: 'tool', color: 'var(--warn)' },
  reply: { label: 'socra', color: 'var(--accent)' },
  error: { label: 'error', color: 'var(--danger)' },
  handoff: { label: '', color: 'var(--label-3)' },
}

/** Code goes to the code pane; the log keeps a pointer to it where the block was. */
function CodePointer({ lang, lines }: { lang: string; lines: number }) {
  return (
    <span data-testid="code-pointer" className="t-small block" style={{ color: 'var(--label-3)' }}>
      {['code panel', lang, `${lines} ${lines === 1 ? 'line' : 'lines'}`].filter(Boolean).join(' · ')}
    </span>
  )
}

function MarkdownBody({ text, color }: { text: string; color: string }) {
  return (
    <div className="flex flex-col gap-2" style={{ color }}>
      {codeSegments(text).map((segment, i) =>
        segment.kind === 'code' ? (
          <CodePointer key={i} lang={segment.lang} lines={segment.lines} />
        ) : (
          <MarkdownText key={i} text={segment.text} />
        ),
      )}
    </div>
  )
}

function Body({ entry }: { entry: TimelineEntry }) {
  switch (entry.kind) {
    case 'user':
      return <MarkdownBody text={entry.text} color="var(--label-2)" />
    case 'tool':
      return (
        <span className="flex min-w-0 gap-[1ch]" style={{ color: 'var(--warn)' }}>
          <span className="shrink-0">{entry.tool}</span>
          {entry.text && (
            <span className="t-mono min-w-0 truncate pt-[0.15em]" title={entry.text} style={{ color: 'var(--label-2)' }}>
              {entry.text}
            </span>
          )}
        </span>
      )
    case 'text':
    case 'reply':
      return <MarkdownBody text={entry.text} color={entry.kind === 'text' ? 'var(--label-2)' : 'var(--label)'} />
    case 'error':
      return <span style={{ color: 'var(--danger)' }}>{entry.text}</span>
    case 'handoff':
      return (
        <span className="t-small flex items-center gap-[1ch]" style={{ color: 'var(--label-3)' }}>
          <span className="h-px w-[3ch] shrink-0" style={{ background: 'var(--hairline, currentColor)', opacity: 0.5 }} aria-hidden="true" />
          {entry.text}
          <span className="h-px min-w-0 flex-1" style={{ background: 'var(--hairline, currentColor)', opacity: 0.5 }} aria-hidden="true" />
        </span>
      )
  }
}

export function AgentTimeline({ entries, protocolState }: AgentTimelineProps) {
  const endRef = useRef<HTMLDivElement>(null)

  // Follow the newest entry once the layout around it has settled (the code pane may have
  // just opened and shortened the conversation).
  const last = entries[entries.length - 1]
  const hasEntries = entries.length > 0
  useEffect(() => {
    const id = requestAnimationFrame(() => endRef.current?.scrollIntoView?.({ block: 'end' }))
    return () => cancelAnimationFrame(id)
  }, [entries.length, last?.text])

  // The split animation keeps shrinking the conversation after that; stay at the end through it.
  useEffect(() => {
    const scroller = endRef.current?.closest('.shell-scroll')
    if (!scroller || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => endRef.current?.scrollIntoView?.({ block: 'end' }))
    observer.observe(scroller)
    return () => observer.disconnect()
    // The end marker only exists once there are entries.
  }, [hasEntries])

  if (entries.length === 0) {
    return (
      <p data-testid="timeline-empty" className="t-ui m-0 py-4" style={{ color: 'var(--label-2)' }}>
        {protocolState === 'listening'
          ? 'Speak or type what you want to study.'
          : 'The conversation will appear here.'}
      </p>
    )
  }

  return (
    <div className="w-full">
      <ol aria-label="Conversation" className="t-read m-0 flex list-none flex-col gap-3 p-0 [overflow-wrap:anywhere] select-text">
        {entries.map((entry) => (
          <li
            key={entry.id}
            data-kind={entry.kind}
            className="grid min-w-0 grid-cols-[6ch_minmax(0,1fr)] gap-x-[1.5ch]"
          >
            <span className="t-small pt-[0.15em] text-right" style={{ color: WHO[entry.kind].color }} aria-hidden="true">
              {WHO[entry.kind].label}
            </span>
            <Body entry={entry} />
          </li>
        ))}
      </ol>
      <div ref={endRef} />
    </div>
  )
}
