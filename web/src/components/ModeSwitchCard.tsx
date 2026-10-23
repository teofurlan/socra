import { useId } from 'react'
import { Repeat2 } from 'lucide-react'
import type { AgentMode, ModeSwitchRequest } from '@/types/agent'

interface ModeSwitchCardProps {
  request: ModeSwitchRequest | null
  onAnswer: (mode: AgentMode, allow: boolean) => void
}

/** The agent asked by voice to change mode; nothing changes until the user accepts here. */
export function ModeSwitchCard({ request, onAnswer }: ModeSwitchCardProps) {
  const titleId = useId()
  if (!request) return null

  return (
    <div
      role="group"
      aria-labelledby={titleId}
      data-testid="mode-switch-request"
      className="flex w-full max-w-[72ch] flex-col gap-3 rounded-lg border p-4"
      style={{ borderColor: 'var(--seam)', background: 'var(--panel)' }}
    >
      <div className="flex items-start gap-3">
        <Repeat2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" style={{ color: 'var(--accent)' }} strokeWidth={2} />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <h2 id={titleId} className="t-ui m-0 font-semibold" style={{ color: 'var(--label)' }}>
            {`Switch to ${request.label} mode?`}
          </h2>
          <span className="t-small" style={{ color: 'var(--label-2)' }}>
            The conversation continues in a new session with a summary of this one.
          </span>
        </div>
      </div>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={() => onAnswer(request.mode, false)} className="key">
          Not now
        </button>
        <button type="button" onClick={() => onAnswer(request.mode, true)} className="key" data-tone="primary">
          Switch
        </button>
      </div>
    </div>
  )
}
