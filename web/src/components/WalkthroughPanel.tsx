import { Pause, Play, RotateCcw, SkipBack, SkipForward, Square } from 'lucide-react'
import type { ReactNode } from 'react'
import type { WalkthroughAction, WalkthroughData } from '@/types/exam'

interface WalkthroughPanelProps {
  walkthrough: WalkthroughData
  onControl: (action: WalkthroughAction) => void
}

const ENDED_TEXT: Record<string, string> = {
  completed: 'Walkthrough finished',
  stopped: 'Walkthrough stopped',
  disconnected: 'Walkthrough ended: the connection was lost',
  error: 'Walkthrough ended: the voice failed',
}

function Control({ label, icon, onClick }: { label: string; icon: ReactNode; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="t-small inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 hover:bg-[var(--raise)]"
      style={{ color: 'var(--label-2)' }}
    >
      {icon}
      {label}
    </button>
  )
}

/** What Socra is saying about the code, and the controls to steer it. */
export function WalkthroughPanel({ walkthrough, onControl }: WalkthroughPanelProps) {
  const { step, status, reason } = walkthrough
  const icon = 'h-3.5 w-3.5'
  const ended = status === 'ended'

  return (
    <div data-testid="walkthrough-panel" className="flex w-full min-w-0 max-w-[72ch] flex-col gap-4">
      <section className="grid grid-cols-[6ch_minmax(0,1fr)] gap-x-[1.5ch] gap-y-1">
        <span className="t-small flex flex-col items-end pt-[0.2em]">
          <span style={{ color: 'var(--accent)' }} aria-hidden="true">
            socra
          </span>
          <span data-testid="walkthrough-progress" className="tabular-nums" style={{ color: 'var(--label-3)' }}>
            {step ? `Step ${step.index}/${step.total}` : 'Starting'}
          </span>
        </span>
        <p
          className="m-0 text-[1rem] leading-[1.65] font-medium [overflow-wrap:anywhere] select-text"
          style={{ color: 'var(--label)', textWrap: 'pretty' }}
        >
          {step?.say ?? ''}
        </p>
      </section>

      {ended ? (
        <p role="status" className="t-small m-0" style={{ color: 'var(--label-2)' }}>
          {ENDED_TEXT[reason ?? 'completed'] ?? ENDED_TEXT.completed}
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Walkthrough controls">
            <Control label="Back" icon={<SkipBack aria-hidden="true" className={icon} />} onClick={() => onControl('back')} />
            <Control label="Repeat" icon={<RotateCcw aria-hidden="true" className={icon} />} onClick={() => onControl('repeat')} />
            {status === 'paused' ? (
              <Control label="Resume" icon={<Play aria-hidden="true" className={icon} />} onClick={() => onControl('resume')} />
            ) : (
              <Control label="Pause" icon={<Pause aria-hidden="true" className={icon} />} onClick={() => onControl('pause')} />
            )}
            <Control label="Next" icon={<SkipForward aria-hidden="true" className={icon} />} onClick={() => onControl('next')} />
            <Control label="Stop" icon={<Square aria-hidden="true" className={icon} />} onClick={() => onControl('stop')} />
          </div>
          {status === 'paused' && (
            <p className="t-small m-0" style={{ color: 'var(--label-3)' }}>
              Paused. Say or type: repeat, back, next, continue or stop.
            </p>
          )}
        </>
      )}
    </div>
  )
}
