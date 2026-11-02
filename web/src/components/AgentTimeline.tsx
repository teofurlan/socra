import { useEffect, useRef } from 'react'
import { centeredScrollTop, findSpokenText } from '@/lib/spokenHighlight'
import { codeSegments } from '@/lib/codeBlocks'
import type { ProtocolState } from '@/types/exam'
import type { SpokenClip, TimelineEntry } from '@/types/agent'
import { MarkdownText } from './MarkdownText'

interface AgentTimelineProps {
  entries: TimelineEntry[]
  protocolState: ProtocolState
  /** The reply clip playing now; its text is drawn with more contrast than the rest. */
  spoken?: SpokenClip | null
}

const HIGHLIGHT_NAME = 'socra-spoken'

/** Marks a range with the CSS Custom Highlight API, which leaves the markup untouched. Returns false without the API. */
function paintHighlight(range: Range | null): boolean {
  const registry = (globalThis.CSS as { highlights?: Map<string, unknown> } | undefined)?.highlights
  const HighlightClass = (globalThis as { Highlight?: new (...ranges: Range[]) => unknown }).Highlight
  if (!registry || !HighlightClass) return false
  if (range) registry.set(HIGHLIGHT_NAME, new HighlightClass(range))
  else registry.delete(HIGHLIGHT_NAME)
  return true
}

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

/** Scrolls the conversation so the range is vertically centred; instant under reduced motion. */
function centerRange(range: Range, scroller: Element | null, spacer: HTMLElement | null) {
  if (!scroller || typeof range.getBoundingClientRect !== 'function') return
  if (spacer) spacer.style.height = `${scroller.clientHeight / 2}px`
  const top = centeredScrollTop(
    range.getBoundingClientRect(), scroller.getBoundingClientRect(), scroller.scrollTop, scroller.clientHeight,
  )
  scroller.scrollTo?.({ top, behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
}

function textNodesOf(root: Element): Text[] {
  const nodes: Text[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text)
  return nodes
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
      return <MarkdownBody text={entry.text} color="var(--transcript)" />
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
      return <MarkdownBody text={entry.text} color="var(--transcript)" />
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

export function AgentTimeline({ entries, protocolState, spoken = null }: AgentTimelineProps) {
  const endRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLOListElement>(null)
  // Letters consumed so far in one entry: the next clip is searched after the previous one.
  const cursorRef = useRef<{ entry: number; consumed: number }>({ entry: 0, consumed: 0 })
  const spacerRef = useRef<HTMLDivElement>(null)
  // True while a clip is highlighted: centering owns the scroll position, follow-the-end waits.
  const highlightedRef = useRef(false)
  const centeredRef = useRef<number | null>(null)

  // Follow the newest entry once the layout around it has settled (the code pane may have
  // just opened and shortened the conversation).
  const last = entries[entries.length - 1]
  const hasEntries = entries.length > 0
  useEffect(() => {
    const id = requestAnimationFrame(() => {
      if (!highlightedRef.current) endRef.current?.scrollIntoView?.({ block: 'end' })
    })
    return () => cancelAnimationFrame(id)
  }, [entries.length, last?.text])

  // The split animation keeps shrinking the conversation after that; stay at the end through it.
  useEffect(() => {
    const scroller = endRef.current?.closest('.shell-scroll')
    if (!scroller || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      if (!highlightedRef.current) endRef.current?.scrollIntoView?.({ block: 'end' })
    })
    observer.observe(scroller)
    return () => observer.disconnect()
    // The end marker only exists once there are entries.
  }, [hasEntries])

  // A new user turn drops the bottom space kept after speech; follow-the-end takes over again.
  const lastKind = last?.kind
  useEffect(() => {
    if (lastKind === 'user' && spacerRef.current) spacerRef.current.style.height = '0px'
  }, [lastKind, entries.length])

  // Highlight the playing clip in the newest entries Socra said, and scroll it to the middle of
  // the conversation like a teleprompter. Never throws: without the API or a match the text
  // stays unmarked and the scroll position is left alone.
  useEffect(() => {
    const clear = () => {
      highlightedRef.current = false
      centeredRef.current = null
      paintHighlight(null)
    }
    try {
      const candidates = [...entries].reverse().filter((e) => e.kind === 'text' || e.kind === 'reply')
      if (!spoken || !listRef.current) return clear()
      for (const target of candidates) {
        const body = listRef.current.querySelector(`[data-entry-id="${target.id}"]`)
        if (!body) continue
        const nodes = textNodesOf(body)
        const texts = nodes.map((node) => node.data)
        const previous = cursorRef.current.entry === target.id ? cursorRef.current.consumed : 0
        const match = findSpokenText(texts, spoken.text, previous) ?? findSpokenText(texts, spoken.text, 0)
        if (!match) continue
        const range = document.createRange()
        range.setStart(nodes[match.start.node], match.start.offset)
        range.setEnd(nodes[match.end.node], match.end.offset)
        if (!paintHighlight(range)) return clear()
        cursorRef.current = { entry: target.id, consumed: match.consumed }
        highlightedRef.current = true
        if (centeredRef.current !== spoken.id) {
          centeredRef.current = spoken.id
          centerRange(range, body.closest('.shell-scroll'), spacerRef.current)
        }
        return
      }
      clear()
    } catch {
      try { clear() } catch { /* no highlight API */ }
    }
  }, [spoken, entries])

  // Never leave a mark behind when the page goes away.
  useEffect(() => () => { try { paintHighlight(null) } catch { /* no highlight API */ } }, [])

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
      <ol ref={listRef} aria-label="Conversation" className="transcript t-read m-0 flex list-none flex-col gap-3 p-0 [overflow-wrap:anywhere] select-text">
        {entries.map((entry) => (
          <li
            key={entry.id}
            data-kind={entry.kind}
            data-entry-id={entry.id}
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
      {/* Room below the last line so a clip near the end can still reach the middle. Kept after
          speech (removing it would clamp the scroll and jump) until the next user turn. Its height
          is set on the element directly because it must exist before the range is measured. */}
      <div ref={spacerRef} data-testid="speech-spacer" aria-hidden="true" style={{ height: 0 }} />
    </div>
  )
}
