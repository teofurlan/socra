import type { ReactNode } from 'react'
import { ConnectionIndicator } from '@/components/ConnectionIndicator'
import type { ConnectionStatus } from '@/types/exam'
import { modeHref } from '@/lib/page'

interface TopBarProps {
  page: 'exam' | 'agent'
  connection: ConnectionStatus
  /** Context chips: question progress, model, folder. */
  chips?: ReactNode
  /** The settings menu, last on the right. */
  menu: ReactNode
}

const TABS = [
  { id: 'exam', label: 'Exam' },
  { id: 'agent', label: 'Study' },
] as const

/** The console's top bar: wordmark, the two modes, context chips, connection and settings. */
export function TopBar({ page, connection, chips, menu }: TopBarProps) {
  return (
    <header className="flex min-h-11 min-w-0 items-center gap-3 border-b px-3 sm:px-4" style={{ borderColor: 'var(--seam)', background: 'var(--bg)' }}>
      <h1 className="m-0 shrink-0 text-[0.9375rem] font-semibold tracking-[-0.01em]">Socra</h1>
      <nav aria-label="Mode" className="flex shrink-0 items-center gap-1">
        {TABS.map((tab) => {
          const current = tab.id === page
          return (
            <a
              key={tab.id}
              href={modeHref(tab.id, window.location.search)}
              aria-current={current ? 'page' : undefined}
              className="t-small rounded-md px-2.5 py-1 no-underline hover:text-[var(--label)]"
              style={{
                color: current ? 'var(--label)' : 'var(--label-2)',
                background: current ? 'var(--raise)' : undefined,
                fontWeight: current ? 600 : 400,
              }}
            >
              {tab.label}
            </a>
          )
        })}
      </nav>
      <div className="hidden min-w-0 items-center gap-2 md:flex">{chips}</div>
      <div className="ml-auto flex shrink-0 items-center gap-2">
        <ConnectionIndicator status={connection} />
        {menu}
      </div>
    </header>
  )
}

/** One context fact in the top bar. */
export function Chip({ children, title, mono = false, testId }: { children: ReactNode; title?: string; mono?: boolean; testId?: string }) {
  return (
    <span className={`chip${mono ? ' t-mono' : ''}`} title={title} data-testid={testId}>
      <span className="min-w-0 truncate">{children}</span>
    </span>
  )
}
