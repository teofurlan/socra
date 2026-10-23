import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import { Panel } from '@/components/shell/Panel'
import { highlight, type TokenKind } from '@/lib/highlight'

/** Syntax colours drawn from the same palette as the state colours. */
const TOKEN_COLOR: Record<TokenKind, string | undefined> = {
  plain: undefined,
  keyword: 'var(--violet)',
  string: 'var(--live)',
  number: 'var(--orange)',
  comment: 'var(--label-3)',
  call: 'var(--accent)',
}

interface CodePaneProps {
  code: string
  /** Shown in the header, e.g. the language or "question 2". */
  name: string
  /** Region name for assistive tech. */
  label: string
  /** Fence language, when known; it decides how comments are read. */
  lang?: string
  /** 1-based inclusive line range being talked about; null or absent highlights nothing. */
  focus?: [number, number] | null
  onClose: () => void
}

/** The right-hand panel: line-numbered code, scrolling inside its own region. */
export function CodePane({ code, name, label, lang = '', focus = null, onClose }: CodePaneProps) {
  const lines = code.replace(/\n$/, '').split('\n')
  const width = String(lines.length).length
  const firstFocused = useRef<HTMLSpanElement | null>(null)
  const focusStart = focus?.[0]
  const focusEnd = focus?.[1]

  useEffect(() => {
    firstFocused.current?.scrollIntoView?.({ block: 'nearest', behavior: 'smooth' })
  }, [focusStart, focusEnd])

  return (
    <Panel
      label={label}
      testId="code-pane"
      className="h-full"
      title={<span>Code</span>}
      meta={
        <>
          <span className="t-mono truncate" style={{ color: 'var(--label-3)' }}>
            {name} · {lines.length} {lines.length === 1 ? 'line' : 'lines'}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close code"
            title="Close the code panel"
            className="-mr-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md hover:bg-[var(--raise)] hover:text-[var(--label)]"
            style={{ color: 'var(--label-2)' }}
          >
            <X aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
          </button>
        </>
      }
    >
      <pre tabIndex={0} className="t-code m-0 min-h-0 flex-1 overflow-auto py-3.5 select-text">
        {/* As wide as the longest line, so its right padding scrolls clear of the edge. */}
        <code className="block w-max min-w-full">
          {lines.map((line, i) => (
            <span
              key={i}
              ref={i + 1 === focusStart ? firstFocused : undefined}
              data-focused={focusStart !== undefined && focusEnd !== undefined && i + 1 >= focusStart && i + 1 <= focusEnd ? 'true' : undefined}
              className="code-line block whitespace-pre pr-4"
            >
              <span
                aria-hidden="true"
                className="mr-4 inline-block select-none text-right tabular-nums"
                style={{ width: `${width + 3}ch`, color: 'var(--label-3)' }}
              >
                {i + 1}
              </span>
              <span>
                {line
                  ? highlight(line, lang).map((t, j) => (
                      <span
                        key={j}
                        data-token={t.kind === 'plain' ? undefined : t.kind}
                        style={{ color: TOKEN_COLOR[t.kind], fontStyle: t.kind === 'comment' ? 'italic' : undefined }}
                      >
                        {t.text}
                      </span>
                    ))
                  : ' '}
              </span>
            </span>
          ))}
        </code>
      </pre>
    </Panel>
  )
}
