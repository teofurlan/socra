import React, { useEffect, useState, useCallback, useRef } from 'react'
import { Mic } from 'lucide-react'

export interface PushToTalkControlProps {
  onTalkingChange?: (isTalking: boolean) => void
}

export const PushToTalkControl: React.FC<PushToTalkControlProps> = ({
  onTalkingChange,
}) => {
  const [isPressed, setIsPressed] = useState<boolean>(false)
  const isPressedRef = useRef<boolean>(false)

  const setTalking = useCallback(
    (pressed: boolean) => {
      if (isPressedRef.current !== pressed) {
        isPressedRef.current = pressed
        setIsPressed(pressed)
        onTalkingChange?.(pressed)
      }
    },
    [onTalkingChange]
  )

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        const target = e.target as HTMLElement | null
        if (
          target &&
          (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.isContentEditable)
        ) {
          return
        }
        e.preventDefault()
        if (!e.repeat) setTalking(true)
      }
    }

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        const target = e.target as HTMLElement | null
        if (
          target &&
          (target.tagName === 'INPUT' ||
            target.tagName === 'TEXTAREA' ||
            target.isContentEditable)
        ) {
          // Releasing an existing hold must work even if focus moved while held.
          if (isPressedRef.current) setTalking(false)
          return
        }
        e.preventDefault()
        setTalking(false)
      }
    }

    const handleWindowBlur = () => {
      setTalking(false)
    }

    window.addEventListener('keydown', handleKeyDown)
    window.addEventListener('keyup', handleKeyUp)
    window.addEventListener('blur', handleWindowBlur)

    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      window.removeEventListener('keyup', handleKeyUp)
      window.removeEventListener('blur', handleWindowBlur)
    }
  }, [setTalking])

  return (
    <div className="flex min-w-0 max-w-full items-center">
      <button
        type="button"
        data-testid="ptt-button"
        data-talking={isPressed}
        aria-pressed={isPressed}
        onMouseDown={() => setTalking(true)}
        onMouseUp={() => setTalking(false)}
        onMouseLeave={() => setTalking(false)}
        onTouchStart={(e) => {
          e.preventDefault()
          setTalking(true)
        }}
        onTouchEnd={(e) => {
          e.preventDefault()
          setTalking(false)
        }}
        onTouchCancel={() => setTalking(false)}
        aria-label={isPressed ? 'Transcribing answer...' : 'Hold to speak (or Space)'}
        title={isPressed ? 'Transcribing answer...' : 'Hold to speak (or Space)'}
        className="key select-none"
        data-shape="square"
        data-tone={isPressed ? 'danger' : undefined}
        style={isPressed ? { background: 'color-mix(in srgb, var(--danger) 16%, transparent)' } : undefined}
      >
        <Mic aria-hidden="true" className="h-4 w-4 shrink-0" strokeWidth={2.2} />
      </button>
    </div>
  )
}
