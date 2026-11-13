import React, { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Ellipsis } from 'lucide-react'
import { ChoiceList } from '@/components/ChoiceList'
import { ModeToggle } from '@/components/ModeToggle'
import { ORB_PALETTES, STATE_PALETTES } from '@/components/orbPalettes'
import {
  DEFAULT_SHAPE,
  SHAPES,
  type ShapeId,
} from '@/components/visualizers'
import type { Microphone } from '@/hooks/useAudioInputs'
import { MIN_SILENCE_TIMEOUT_MS, MAX_SILENCE_TIMEOUT_MS } from '@/lib/storage'
import { THEME_PREFS, type ThemePref } from '@/lib/theme'
import type { TurnMode } from '@/types/exam'

export interface SettingsMenuProps {
  mode: TurnMode
  onModeChange: (mode: TurnMode) => void
  silenceTimeoutMs: number
  onSilenceChange: (ms: number) => void
  paletteId: string
  onPaletteChange: (id: string) => void
  /** Omit onShapeChange to hide the shape choice. */
  shape?: ShapeId
  onShapeChange?: (id: ShapeId) => void
  microphones: Microphone[]
  /** '' = system default. */
  micDeviceId: string
  onMicChange: (deviceId: string) => void
  /** Capture is using the system default because the selected microphone failed. */
  micFallback: boolean
  /** Called each time the menu opens, to refresh the device list. */
  onOpen?: () => void
  themePref: ThemePref
  onThemeChange: (pref: ThemePref) => void
  /** Omit to hide the voice choice. */
  voicePicker?: ReactNode
  /** Spoken turns wait in the composer for Enter. Omit onReviewDictationChange to hide the switch. */
  reviewDictation?: boolean
  onReviewDictationChange?: (review: boolean) => void
}

function Section({ title, children, testId }: { title: ReactNode; children: ReactNode; testId?: string }) {
  return (
    <section className="flex flex-col gap-2" data-testid={testId}>
      <h2 className="t-head m-0">{title}</h2>
      {children}
    </section>
  )
}

/** A "…" button at the end of the top bar; every setting lives in the panel below it. */
export const SettingsMenu: React.FC<SettingsMenuProps> = ({
  mode,
  onModeChange,
  silenceTimeoutMs,
  onSilenceChange,
  paletteId,
  onPaletteChange,
  shape = DEFAULT_SHAPE,
  onShapeChange,
  microphones,
  micDeviceId,
  onMicChange,
  micFallback,
  onOpen,
  themePref,
  onThemeChange,
  voicePicker,
  reviewDictation = false,
  onReviewDictationChange,
}) => {
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const panelId = useId()

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false)
        buttonRef.current?.focus()
      }
    }
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('keydown', onKey)
    window.addEventListener('pointerdown', onPointer)
    return () => {
      window.removeEventListener('keydown', onKey)
      window.removeEventListener('pointerdown', onPointer)
    }
  }, [open])

  const palettes: { id: string; name: string; colors: [string, string] }[] = [
    { id: 'state', name: 'By state', colors: [STATE_PALETTES.listening[0], STATE_PALETTES.speaking[0]] },
    ...ORB_PALETTES,
  ]

  // An empty list means names are hidden until access is granted, not that the device is gone.
  const micMissing =
    micDeviceId !== '' && microphones.length > 0 && !microphones.some((m) => m.deviceId === micDeviceId)

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        data-testid="settings-button"
        aria-label="Settings"
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={panelId}
        title="Settings"
        onClick={() => {
          if (!open) onOpen?.()
          setOpen(!open)
        }}
        className="grid h-8 w-8 place-items-center rounded-md border hover:bg-[var(--raise)] hover:text-[var(--label)]"
        style={{
          borderColor: open ? 'var(--seam-strong)' : 'transparent',
          background: open ? 'var(--raise)' : undefined,
          color: open ? 'var(--label)' : 'var(--label-2)',
        }}
      >
        <Ellipsis aria-hidden="true" className="h-4 w-4" strokeWidth={2.25} />
      </button>

      {open && (
        <div
          id={panelId}
          role="dialog"
          aria-label="Settings"
          data-testid="settings-panel"
          className="absolute top-[calc(100%+8px)] right-0 z-30 flex max-h-[calc(100dvh-4.5rem)] w-[min(22rem,calc(100vw-1rem))] flex-col gap-5 overflow-y-auto rounded-lg border p-4"
          style={{ background: 'var(--panel)', borderColor: 'var(--seam-strong)', boxShadow: '0 16px 40px -16px rgba(0,0,0,0.45)' }}
        >
          <Section title="Theme">
            <div role="radiogroup" aria-label="Theme" className="grid grid-cols-3 gap-1">
              {THEME_PREFS.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  role="radio"
                  aria-checked={themePref === t.id}
                  data-testid={`theme-${t.id}`}
                  onClick={() => onThemeChange(t.id)}
                  className="key t-small min-h-8"
                >
                  {t.name}
                </button>
              ))}
            </div>
          </Section>

          <Section title="Microphone" testId="mic-control">
            <ChoiceList
              label="Microphone"
              value={micDeviceId}
              onChange={onMicChange}
              groups={[
                {
                  choices: [
                    { value: '', label: 'System default' },
                    ...microphones.map((m) => ({ value: m.deviceId, label: m.label })),
                    ...(micMissing ? [{ value: micDeviceId, label: 'Disconnected microphone', note: 'unplugged', disabled: true }] : []),
                  ],
                },
              ]}
            />
            {(micMissing || micFallback) && (
              <p data-testid="mic-fallback-note" className="t-small m-0" style={{ color: 'var(--warn)' }}>
                The selected microphone is not available. Using the system default.
              </p>
            )}
            {microphones.length === 0 && (
              <p className="t-small m-0" style={{ color: 'var(--label-2)' }}>
                Allow microphone access to see device names.
              </p>
            )}
          </Section>

          {voicePicker && <Section title="Voice" testId="voice-control">{voicePicker}</Section>}

          <Section title="Turns">
            <ModeToggle mode={mode} onChange={onModeChange} />
            {mode === 'auto' && (
              <div className="flex flex-col" data-testid="silence-timeout-control">
                <label htmlFor={`${panelId}-silence`} className="t-small flex items-center gap-2" style={{ color: 'var(--label-2)' }}>
                  Silence before sending
                  <span className="ml-auto tabular-nums" style={{ color: 'var(--label)' }}>
                    {(silenceTimeoutMs / 1000).toFixed(1)}s
                  </span>
                </label>
                <input
                  id={`${panelId}-silence`}
                  type="range"
                  className="slim w-full"
                  min={MIN_SILENCE_TIMEOUT_MS}
                  max={MAX_SILENCE_TIMEOUT_MS}
                  step={500}
                  value={silenceTimeoutMs}
                  onChange={(e) => onSilenceChange(Number(e.target.value))}
                  aria-label="End-of-answer silence duration"
                />
              </div>
            )}
            {onReviewDictationChange && (
              <label className="t-small flex items-center gap-2" style={{ color: 'var(--label-2)' }} data-testid="review-dictation-control">
                <input
                  type="checkbox"
                  checked={reviewDictation}
                  onChange={(e) => onReviewDictationChange(e.target.checked)}
                />
                Review dictation before sending
              </label>
            )}
          </Section>

          {onShapeChange && (
            <Section title="Shape">
              <div role="radiogroup" aria-label="Shape" className="grid grid-cols-2 gap-1">
                {SHAPES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    role="radio"
                    aria-checked={shape === s.id}
                    data-testid={`shape-${s.id}`}
                    onClick={() => onShapeChange(s.id)}
                    className="key t-small min-h-8"
                  >
                    {s.name}
                  </button>
                ))}
              </div>
            </Section>
          )}

          <Section title="Particle colors">
            <div role="radiogroup" aria-label="Particle colors" className="grid grid-cols-2 gap-1">
              {palettes.map((o) => {
                const active = paletteId === o.id
                return (
                  <button
                    key={o.id}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    data-testid={`palette-${o.id}`}
                    onClick={() => onPaletteChange(o.id)}
                    className="t-small flex min-h-8 items-center gap-[1.25ch] rounded-[3px] px-[1ch] text-left hover:bg-[var(--raise)]"
                    style={{ color: active ? 'var(--label)' : 'var(--label-2)', background: active ? 'var(--raise)' : undefined }}
                  >
                    <span aria-hidden="true" className="flex shrink-0">
                      <span className="h-3 w-2" style={{ background: o.colors[0] }} />
                      <span className="h-3 w-2" style={{ background: o.colors[1] }} />
                    </span>
                    {o.name}
                    {active && <span aria-hidden="true" className="ml-auto h-[5px] w-[5px] rounded-full" style={{ background: 'var(--accent)' }} />}
                  </button>
                )
              })}
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}
