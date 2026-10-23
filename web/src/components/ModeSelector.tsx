import { useId } from 'react'
import { AGENT_MODES, type AgentMode } from '@/types/agent'

interface ModeSelectorProps {
  mode: AgentMode
  onChange: (mode: AgentMode) => void
  disabled?: boolean
  /** Why the selector is disabled, shown next to it. */
  reason?: string
  /** The mode a handoff is switching to, while it runs. */
  switching?: AgentMode | null
}

/** Agent, mentor or exam: the mode of the project session, next to the folder and model. */
export function ModeSelector({ mode, onChange, disabled = false, reason, switching = null }: ModeSelectorProps) {
  const reasonId = useId()
  const locked = disabled || switching !== null
  const target = AGENT_MODES.find((m) => m.id === switching)

  return (
    <div className="mode-selector flex min-w-0 items-center gap-2">
      <div
        role="radiogroup"
        aria-label="Mode"
        aria-busy={switching !== null}
        aria-describedby={reason ? reasonId : undefined}
        className="flex items-center gap-1"
      >
        {AGENT_MODES.map(({ id, label }) => (
          <button
            key={id}
            type="button"
            role="radio"
            aria-checked={id === mode}
            disabled={locked}
            onClick={() => {
              if (id !== mode) onChange(id)
            }}
            className="key"
            style={{ minHeight: 32, paddingInline: 10 }}
          >
            {label}
          </button>
        ))}
      </div>
      {reason && (
        <span id={reasonId} className="t-small min-w-0 truncate" style={{ color: 'var(--label-3)' }}>
          {reason}
        </span>
      )}
      {target && (
        <span role="status" className="t-small min-w-0 truncate" style={{ color: 'var(--label-2)' }}>
          {`Switching to ${target.label}…`}
        </span>
      )}
    </div>
  )
}
