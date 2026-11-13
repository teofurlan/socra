/**
 * useMicCapture tests — public interface only.
 * Mocks: navigator.mediaDevices.getUserMedia, @ricky0123/vad-web, AudioContext.
 * One test per S3 rule.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { render, screen, fireEvent } from '@testing-library/react'
import App from '@/App'

vi.mock('@/components/ui/orb', () => ({ Orb: () => <div /> }))
import { useMicCapture } from '@/hooks/useMicCapture'
import type { ProtocolState, TurnMode } from '@/types/exam'
import {
  getStoredSilenceTimeout,
  setStoredSilenceTimeout,
  DEFAULT_SILENCE_TIMEOUT_MS,
  STORAGE_KEY_SILENCE_TIMEOUT,
} from '@/lib/storage'

// ─── VAD module mock ──────────────────────────────────────────────────────────

type VADCallbacks = {
  onSpeechStart?: () => void
  onSpeechEnd?: (audio: Float32Array) => void
  onVADMisfire?: () => void
  onFrameProcessed?: (probabilities: { isSpeech: number; notSpeech: number }, frame: Float32Array) => void
}

let lastVADCallbacks: VADCallbacks = {}
let vadDestroyFn = vi.fn(async () => {})

vi.mock('@ricky0123/vad-web', () => ({
  MicVAD: {
    new: vi.fn(async (opts: VADCallbacks) => {
      lastVADCallbacks = {
        onSpeechStart: opts.onSpeechStart,
        onSpeechEnd: opts.onSpeechEnd,
        onVADMisfire: opts.onVADMisfire,
        onFrameProcessed: opts.onFrameProcessed,
      }
      return { start: vi.fn(async () => {}), destroy: vadDestroyFn }
    }),
  },
}))

const { MicVAD } = await import('@ricky0123/vad-web')

// ─── Audio infrastructure mocks ───────────────────────────────────────────────

type OnaudioprocessFn =
  | ((e: { inputBuffer: { getChannelData: (ch: number) => Float32Array } }) => void)
  | null

class MockScriptProcessor {
  onaudioprocess: OnaudioprocessFn = null
  connect = vi.fn()
  disconnect = vi.fn()
}

let activeScriptProcessor: MockScriptProcessor | null = null
let contexts: MockAudioContext[] = []

class MockAnalyser {
  fftSize = 512
  connect = vi.fn()
  disconnect = vi.fn()
  getByteTimeDomainData(arr: Uint8Array) {
    arr.fill(160) // non-silent
  }
}

class MockMediaStreamSourceNode {
  connect = vi.fn()
  disconnect = vi.fn()
}

class MockAudioContext {
  constructor() { contexts.push(this) }
  state = 'running'
  sampleRate = 44100
  destination = {}
  _analyser = new MockAnalyser()
  _source = new MockMediaStreamSourceNode()

  createAnalyser() {
    return this._analyser
  }
  createMediaStreamSource(_s: MediaStream) {
    return this._source
  }
  createScriptProcessor(_b: number, _i: number, _o: number) {
    const proc = new MockScriptProcessor()
    activeScriptProcessor = proc
    return proc
  }
  close = vi.fn(async () => {})
}

// ─── MediaStream / getUserMedia mocks ─────────────────────────────────────────

function makeTrack() {
  return { stop: vi.fn(), kind: 'audio' } as unknown as MediaStreamTrack
}

function makeMockStream() {
  const tracks = [makeTrack()]
  return {
    getTracks: () => tracks,
    getAudioTracks: () => tracks,
  } as unknown as MediaStream
}

let getUserMediaResult: MediaStream | null = null
let getUserMediaError: Error | null = null

function setupGetUserMedia() {
  vi.stubGlobal('navigator', {
    ...globalThis.navigator,
    mediaDevices: {
      getUserMedia: vi.fn(async () => {
        if (getUserMediaError) throw getUserMediaError
        if (!getUserMediaResult) throw new Error('no stream')
        return getUserMediaResult
      }),
    },
  })
}

// ─── Helper: default hook options ────────────────────────────────────────────

function makeOpts(
  protocolState: ProtocolState = 'listening',
  mode: TurnMode = 'auto',
  onFinalize = vi.fn(),
): Parameters<typeof useMicCapture>[0] {
  return { protocolState, mode, silenceTimeoutMs: 3000, onFinalize }
}

// ─── Global setup / teardown ─────────────────────────────────────────────────

beforeEach(() => {
  lastVADCallbacks = {}
  vadDestroyFn = vi.fn(async () => {})
  ;(MicVAD.new as ReturnType<typeof vi.fn>).mockImplementation(async (opts: VADCallbacks) => {
    lastVADCallbacks = {
      onSpeechStart: opts.onSpeechStart,
      onSpeechEnd: opts.onSpeechEnd,
      onVADMisfire: opts.onVADMisfire,
      onFrameProcessed: opts.onFrameProcessed,
    }
    return { start: vi.fn(async () => {}), destroy: vadDestroyFn }
  })

  getUserMediaResult = makeMockStream()
  getUserMediaError = null
  activeScriptProcessor = null
  contexts = []
  setupGetUserMedia()
  vi.stubGlobal('AudioContext', MockAudioContext)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  window.localStorage.clear()
})

// ─── R1: no capture while state is not listening ──────────────────────────────

describe('R1 — no capture while state is not listening', () => {
  it('does NOT call getUserMedia when protocolState is "speaking"', async () => {
    renderHook(() => useMicCapture(makeOpts('speaking', 'auto')))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  })

  it('does NOT call getUserMedia when protocolState is "thinking"', async () => {
    renderHook(() => useMicCapture(makeOpts('thinking', 'auto')))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  })

  it('does NOT call getUserMedia when protocolState is "idle"', async () => {
    renderHook(() => useMicCapture(makeOpts('idle', 'auto')))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
  })

  it('stops VAD when transitioning from listening to speaking', async () => {
    const { rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: makeOpts('listening', 'auto'),
    })
    await act(async () => {})
    expect(MicVAD.new).toHaveBeenCalledOnce()

    rerender(makeOpts('speaking', 'auto'))
    await act(async () => {})

    expect(vadDestroyFn).toHaveBeenCalledOnce()
  })
})

// ─── R2: auto VAD — silence timer behavior ───────────────────────────────────

describe('R2 — auto VAD accumulates segments and finalizes after silence', () => {
  it('finalizes 3000 ms after the last speech frame, including VAD redemption', async () => {
    const onFinalize = vi.fn()
    const { result } = renderHook(() => useMicCapture(makeOpts('listening', 'auto', onFinalize)))
    await act(async () => {})
    const options = vi.mocked(MicVAD.new).mock.calls[0][0]!
    const redemptionMs = options.redemptionMs ?? 1400

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      // The last speech frame is now; VAD reports its end after redemption.
      setTimeout(() => lastVADCallbacks.onSpeechEnd?.(new Float32Array([0.3])), redemptionMs)
      vi.advanceTimersByTime(redemptionMs)
    })
    expect(result.current.silenceCountdownMs).toBe(3000 - redemptionMs)
    act(() => vi.advanceTimersByTime(3000 - redemptionMs - 1))
    expect(onFinalize).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onFinalize).toHaveBeenCalledOnce()
    expect(result.current.silenceCountdownMs).toBe(0)
    act(() => vi.advanceTimersByTime(3000))
    expect(onFinalize).toHaveBeenCalledOnce()
  })

  it('does not finalize before silence timer fires', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.5))
    })
    // Timer not expired yet
    expect(onFinalize).not.toHaveBeenCalled()
  })

  it('new speech cancels the silence timer (no premature finalization)', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.5))
    })
    act(() => {
      vi.advanceTimersByTime(1500)
    })
    // Student resumes speaking — cancels the timer
    act(() => {
      lastVADCallbacks.onSpeechStart?.()
    })
    // Full timer period passes — no finalization
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(onFinalize).not.toHaveBeenCalled()
  })

  it('finalizes exactly once after silence expires', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.5))
    })
    act(() => {
      vi.advanceTimersByTime(3001)
    })

    expect(onFinalize).toHaveBeenCalledOnce()
  })

  it('accumulates multiple speech segments before finalizing', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.3))
    })
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    act(() => {
      lastVADCallbacks.onSpeechStart?.()
    })
    act(() => {
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.4))
    })
    act(() => {
      vi.advanceTimersByTime(3001)
    })

    expect(onFinalize).toHaveBeenCalledOnce()
  })
})

// ─── R3 / R4: push-to-talk ───────────────────────────────────────────────────

describe('R3 / R4 — push-to-talk behavior', () => {
  it('sends WAV base64 on release after a valid hold (>= 300 ms)', async () => {
    const onFinalize = vi.fn()
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk'), onFinalize }),
    )
    await act(async () => {})

    // Press
    act(() => {
      result.current.onTalkingChange(true)
    })
    await act(async () => {})

    // Simulate captured audio via ScriptProcessor
    const proc = activeScriptProcessor
    expect(proc).not.toBeNull()
    act(() => {
      proc!.onaudioprocess?.({
        inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.3) },
      })
    })

    // Advance past 300 ms hold threshold
    act(() => {
      vi.advanceTimersByTime(400)
    })

    // Release
    await act(async () => {
      result.current.onTalkingChange(false)
    })

    expect(onFinalize).toHaveBeenCalledOnce()
    const [b64] = onFinalize.mock.calls[0] as [string]
    expect(() => atob(b64)).not.toThrow()
  })

  it('ignores hold shorter than 300 ms (no send)', async () => {
    const onFinalize = vi.fn()
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk'), onFinalize }),
    )
    await act(async () => {})

    act(() => {
      result.current.onTalkingChange(true)
    })
    await act(async () => {})

    const proc = activeScriptProcessor
    if (proc) {
      act(() => {
        proc.onaudioprocess?.({
          inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.3) },
        })
      })
    }

    // Only 100 ms — below the 300 ms threshold
    act(() => {
      vi.advanceTimersByTime(100)
    })
    await act(async () => {
      result.current.onTalkingChange(false)
    })

    expect(onFinalize).not.toHaveBeenCalled()
  })
})

// ─── R4: empty / silent capture not sent ─────────────────────────────────────

describe('R4 — empty or silent capture is not sent', () => {
  it('does not call onFinalize when VAD segments contain only silence', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})

    act(() => {
      // All-zero audio → hasSpeech returns false
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0))
    })
    act(() => {
      vi.advanceTimersByTime(3001)
    })

    expect(onFinalize).not.toHaveBeenCalled()
  })

  it('does not call onFinalize when no VAD speech events fired', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts(), onFinalize }))
    await act(async () => {})
    act(() => {
      vi.advanceTimersByTime(10_000)
    })
    expect(onFinalize).not.toHaveBeenCalled()
  })
})

// ─── R6: stream tracks stopped on leaving listening ──────────────────────────

describe('R6 — stream tracks released when leaving listening', () => {
  it('stops stream tracks when protocolState changes away from listening', async () => {
    const stream = makeMockStream()
    getUserMediaResult = stream

    const { rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: makeOpts('listening', 'auto'),
    })
    await act(async () => {})

    rerender(makeOpts('speaking', 'auto'))
    await act(async () => {})

    for (const track of stream.getTracks()) {
      expect((track as unknown as { stop: ReturnType<typeof vi.fn> }).stop).toHaveBeenCalled()
    }
  })

  it('stops stream tracks on unmount', async () => {
    const stream = makeMockStream()
    getUserMediaResult = stream

    const { unmount } = renderHook(() => useMicCapture(makeOpts('listening', 'auto')))
    await act(async () => {})

    unmount()
    await act(async () => {})

    for (const track of stream.getTracks()) {
      expect((track as unknown as { stop: ReturnType<typeof vi.fn> }).stop).toHaveBeenCalled()
    }
  })
})

// ─── R7: permission-denied error is surfaced ─────────────────────────────────

describe('R7 — microphone permission error is surfaced', () => {
  it('sets micError when getUserMedia throws NotAllowedError', async () => {
    getUserMediaError = new DOMException('Permission denied', 'NotAllowedError')

    const { result } = renderHook(() => useMicCapture(makeOpts('listening', 'auto')))
    // getUserMedia rejects; the hook awaits it and then calls setMicError
    await act(async () => {})

    expect(result.current.micError).not.toBeNull()
    expect(result.current.micError).toContain('denied')
  })

  it('sets micError when getUserMedia throws NotFoundError', async () => {
    getUserMediaError = new DOMException('No device', 'NotFoundError')

    const { result } = renderHook(() => useMicCapture(makeOpts('listening', 'auto')))
    await act(async () => {})

    expect(result.current.micError).not.toBeNull()
    expect(result.current.micError).toMatch(/microphone/i)
  })

  it('renders the mic-error banner in the DOM when micError is set', async () => {
    getUserMediaError = new DOMException('Permission denied', 'NotAllowedError')

    function TestBanner() {
      const { micError } = useMicCapture(makeOpts('listening', 'auto'))
      if (!micError) return null
      return (
        <div role="alert" data-testid="mic-error-banner">
          {micError}
        </div>
      )
    }

    const { rerender } = render(<TestBanner />)
    await act(async () => {})
    // Force React to flush state updates from the resolved promise
    rerender(<TestBanner />)

    expect(screen.getByTestId('mic-error-banner')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent(/denied/i)
  })
})

// ─── R8: silence timeout setting persists ────────────────────────────────────

describe('R8 — silence timeout setting persists in localStorage', () => {
  it('returns DEFAULT_SILENCE_TIMEOUT_MS when nothing is stored', () => {
    window.localStorage.clear()
    expect(getStoredSilenceTimeout()).toBe(DEFAULT_SILENCE_TIMEOUT_MS)
  })

  it('persists and retrieves the silence timeout value', () => {
    window.localStorage.clear()
    setStoredSilenceTimeout(5000)
    expect(getStoredSilenceTimeout()).toBe(5000)
  })

  it('does not throw when localStorage.setItem throws', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Quota exceeded')
    })
    expect(() => setStoredSilenceTimeout(4000)).not.toThrow()
  })

  it('returns default when stored value is outside the valid range', () => {
    window.localStorage.clear()
    window.localStorage.setItem(STORAGE_KEY_SILENCE_TIMEOUT, '99999')
    expect(getStoredSilenceTimeout()).toBe(DEFAULT_SILENCE_TIMEOUT_MS)
  })
})

// Validation regressions: interrupted async work must never outlive its turn.
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

function audioFrame() {
  activeScriptProcessor?.onaudioprocess?.({
    inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.3) },
  })
}

describe('T3 validation regressions', () => {
  it('re-arms after a server listening message even when re-answer never leaves listening', async () => {
    class Socket {
      static OPEN = 1
      static instance: Socket
      readyState = 1
      send = vi.fn()
      close = vi.fn()
      onopen = null
      onclose = null
      onerror = null
      onmessage: ((event: MessageEvent) => void) | null = null
      constructor() { Socket.instance = this }
      message(data: unknown) { this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) })) }
    }
    vi.stubGlobal('WebSocket', Socket)
    window.localStorage.setItem('oral_exam_turn_mode', 'push-to-talk')
    render(<App />)
    const socket = Socket.instance
    act(() => socket.message({ type: 'state', state: 'listening' }))
    const hold = async () => {
      fireEvent.mouseDown(screen.getByTestId('ptt-button'))
      await act(async () => {})
      act(() => { audioFrame(); vi.advanceTimersByTime(300) })
      fireEvent.mouseUp(screen.getByTestId('ptt-button'))
      await act(async () => {})
    }
    await hold()
    const answers = () => socket.send.mock.calls.map(([raw]) => JSON.parse(raw)).filter((msg) => msg.type === 'answer_audio')
    expect(answers()).toHaveLength(1)
    expect(answers()[0]).toMatchObject({ type: 'answer_audio', format: 'wav' })
    act(() => socket.message({ type: 'transcript', text: 'First answer', final: true }))
    fireEvent.click(screen.getByTestId('reanswer-button'))
    await hold() // Still latched until the server actually permits another answer.
    expect(answers()).toHaveLength(1)
    act(() => socket.message({ type: 'state', state: 'listening' }))
    await hold()
    expect(answers()).toHaveLength(2)
  })

  it.each(['speaking', 'thinking', 'idle'] as const)('rejects PTT presses while %s', async (state) => {
    const onFinalize = vi.fn()
    const { result } = renderHook(() => useMicCapture(makeOpts(state, 'push-to-talk', onFinalize)))
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).not.toHaveBeenCalled()
    expect(onFinalize).not.toHaveBeenCalled()
  })

  it.each(['speaking', 'mode', 'unmount'] as const)('disposes delayed permission after %s', async (change) => {
    const pending = deferred<MediaStream>()
    const stream = makeMockStream()
    vi.mocked(navigator.mediaDevices.getUserMedia).mockReturnValueOnce(pending.promise)
    const { rerender, unmount } = renderHook((opts) => useMicCapture(opts), {
      initialProps: makeOpts(),
    })
    if (change === 'unmount') unmount()
    else rerender(makeOpts(change === 'mode' ? 'listening' : 'speaking', change === 'mode' ? 'push-to-talk' : 'auto'))
    await act(async () => { pending.resolve(stream) })
    expect(stream.getTracks()[0].stop).toHaveBeenCalled()
    expect(MicVAD.new).not.toHaveBeenCalled()
    expect(contexts).toHaveLength(0)
  })

  it('destroys a late VAD without closing the replacement turn context', async () => {
    const pending = deferred<Awaited<ReturnType<typeof MicVAD.new>>>()
    const lateDestroy = vi.fn(async () => {})
    vi.mocked(MicVAD.new).mockImplementationOnce(() => pending.promise)
    const { rerender } = renderHook((opts) => useMicCapture(opts), { initialProps: makeOpts() })
    await act(async () => {})
    rerender(makeOpts('speaking'))
    rerender(makeOpts())
    await act(async () => {})
    await act(async () => { pending.resolve({ destroy: lateDestroy } as unknown as Awaited<ReturnType<typeof MicVAD.new>>) })
    expect(lateDestroy).toHaveBeenCalledOnce()
    expect(contexts[0].close).toHaveBeenCalledOnce()
    expect(contexts[1].close).not.toHaveBeenCalled()
  })

  it('discards an interrupted PTT hold and releases all audio resources', async () => {
    const onFinalize = vi.fn()
    const stream = getUserMediaResult!
    const { result, rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: makeOpts('listening', 'push-to-talk', onFinalize),
    })
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    const proc = activeScriptProcessor!
    act(() => { audioFrame(); vi.advanceTimersByTime(400) })
    rerender(makeOpts('speaking', 'push-to-talk', onFinalize))
    await act(async () => { result.current.onTalkingChange(false) })
    expect(onFinalize).not.toHaveBeenCalled()
    expect(proc.onaudioprocess).toBeNull()
    expect(proc.disconnect).toHaveBeenCalled()
    expect(stream.getTracks()[0].stop).toHaveBeenCalled()
    expect(contexts[0].close).toHaveBeenCalledOnce()
  })

  it.each(['short', 'empty'] as const)('releases the microphone after a %s PTT hold', async (kind) => {
    const stream = getUserMediaResult!
    const onFinalize = vi.fn()
    const { result } = renderHook(() => useMicCapture(makeOpts('listening', 'push-to-talk', onFinalize)))
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    act(() => { if (kind === 'short') audioFrame(); vi.advanceTimersByTime(kind === 'short' ? 299 : 300) })
    await act(async () => { result.current.onTalkingChange(false) })
    expect(onFinalize).not.toHaveBeenCalled()
    expect(stream.getTracks()[0].stop).toHaveBeenCalled()
    expect(contexts[0].close).toHaveBeenCalledOnce()
  })

  it('stops auto capture after one answer and ignores further VAD events until a new turn', async () => {
    const onFinalize = vi.fn()
    const stream = getUserMediaResult!
    const { rerender } = renderHook((opts) => useMicCapture(opts), { initialProps: makeOpts('listening', 'auto', onFinalize) })
    await act(async () => {})
    const callbacks = lastVADCallbacks
    act(() => { callbacks.onSpeechEnd?.(new Float32Array([0.3])); vi.advanceTimersByTime(3000) })
    await act(async () => {})
    expect(onFinalize).toHaveBeenCalledOnce()
    expect(stream.getTracks()[0].stop).toHaveBeenCalled()
    expect(contexts[0].close).toHaveBeenCalledOnce()
    act(() => { callbacks.onSpeechEnd?.(new Float32Array([0.4])); vi.advanceTimersByTime(3000) })
    expect(onFinalize).toHaveBeenCalledOnce()
    rerender(makeOpts('thinking', 'auto', onFinalize))
    rerender(makeOpts('listening', 'auto', onFinalize))
    await act(async () => {})
    act(() => { lastVADCallbacks.onSpeechEnd?.(new Float32Array([0.5])); vi.advanceTimersByTime(3000) })
    expect(onFinalize).toHaveBeenCalledTimes(2)
  })

  it('sends PTT exactly once, including when the mode changes before the server responds', async () => {
    const onFinalize = vi.fn()
    const { result, rerender } = renderHook((opts) => useMicCapture(opts), { initialProps: makeOpts('listening', 'push-to-talk', onFinalize) })
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    act(() => { audioFrame(); vi.advanceTimersByTime(300) })
    await act(async () => { result.current.onTalkingChange(false) })
    expect(onFinalize).toHaveBeenCalledOnce()
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    act(() => { audioFrame(); vi.advanceTimersByTime(300) })
    await act(async () => { result.current.onTalkingChange(false) })
    rerender(makeOpts('listening', 'auto', onFinalize))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce()
    expect(onFinalize).toHaveBeenCalledOnce()
  })

  it('resumes the silence countdown after a VAD misfire instead of hanging the answer', async () => {
    const onFinalize = vi.fn()
    const { result } = renderHook(() => useMicCapture(makeOpts('listening', 'auto', onFinalize)))
    await act(async () => {})
    act(() => { lastVADCallbacks.onSpeechEnd?.(new Float32Array([0.3])); vi.advanceTimersByTime(1000) })
    act(() => lastVADCallbacks.onSpeechStart?.())
    expect(result.current.silenceCountdownMs).toBe(0)
    act(() => lastVADCallbacks.onVADMisfire?.())
    act(() => vi.advanceTimersByTime(1655)) // 3000 - 1344 ms redemption - 1
    expect(onFinalize).not.toHaveBeenCalled()
    expect(result.current.silenceCountdownMs).toBeGreaterThan(0)
    act(() => vi.advanceTimersByTime(1))
    expect(onFinalize).toHaveBeenCalledOnce()
  })

  it('retains both speech segments in the sent WAV across a thinking pause', async () => {
    const onFinalize = vi.fn()
    renderHook(() => useMicCapture(makeOpts('listening', 'auto', onFinalize)))
    await act(async () => {})
    act(() => { lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.25)); vi.advanceTimersByTime(1655) })
    expect(onFinalize).not.toHaveBeenCalled()
    act(() => { lastVADCallbacks.onSpeechStart?.(); vi.advanceTimersByTime(5000) })
    expect(onFinalize).not.toHaveBeenCalled()
    act(() => { lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(-0.5)); vi.advanceTimersByTime(3000) })
    expect(onFinalize).toHaveBeenCalledOnce()
    const bytes = Uint8Array.from(atob(onFinalize.mock.calls[0][0]), (c) => c.charCodeAt(0))
    const wav = new DataView(bytes.buffer)
    expect(wav.getUint32(40, true)).toBe(640)
    expect(wav.getInt16(44, true)).toBe(8192)
    expect(wav.getInt16(44 + 320, true)).toBe(-16384)
  })
})

// ─── #9: microphone selection ────────────────────────────────────────────────

const PROCESSING = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }

describe('#9 — microphone selection', () => {
  it('opens the selected microphone in automatic mode', async () => {
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), deviceId: 'usb-mic' }))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: { ...PROCESSING, deviceId: { exact: 'usb-mic' } },
    })
  })

  it('keeps using the system default when no microphone is selected', async () => {
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), deviceId: '' }))
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: PROCESSING })
  })

  it('opens the selected microphone for push-to-talk', async () => {
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk'), deviceId: 'usb-mic' }),
    )
    await act(async () => {})
    await act(async () => { result.current.onTalkingChange(true) })
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({
      audio: { ...PROCESSING, deviceId: { exact: 'usb-mic' } },
    })
  })

  it('switches to a newly selected microphone while listening', async () => {
    const first = makeMockStream()
    getUserMediaResult = first
    const onFinalize = vi.fn()
    const { result, rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: { ...makeOpts('listening', 'auto', onFinalize), deviceId: 'mic-a' },
    })
    await act(async () => {})

    const second = makeMockStream()
    getUserMediaResult = second
    rerender({ ...makeOpts('listening', 'auto', onFinalize), deviceId: 'mic-b' })
    await act(async () => {})

    expect(first.getTracks()[0].stop).toHaveBeenCalled()
    expect(vadDestroyFn).toHaveBeenCalledOnce()
    expect(MicVAD.new).toHaveBeenCalledTimes(2)
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenLastCalledWith({
      audio: { ...PROCESSING, deviceId: { exact: 'mic-b' } },
    })
    expect(second.getTracks()[0].stop).not.toHaveBeenCalled()

    // The new microphone still finalizes the turn.
    act(() => { lastVADCallbacks.onSpeechEnd?.(new Float32Array(160).fill(0.25)); vi.advanceTimersByTime(3000) })
    expect(onFinalize).toHaveBeenCalledOnce()
    expect(result.current.micError).toBeNull()
  })

  it('falls back to the system default when the selected microphone is gone', async () => {
    const stream = makeMockStream()
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(async (constraints) => {
      const audio = (constraints as MediaStreamConstraints).audio as MediaTrackConstraints
      if (audio.deviceId) throw new DOMException('Device gone', 'OverconstrainedError')
      return stream
    })

    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'auto'), deviceId: 'unplugged' }),
    )
    await act(async () => {})

    expect(navigator.mediaDevices.getUserMedia).toHaveBeenLastCalledWith({ audio: PROCESSING })
    expect(MicVAD.new).toHaveBeenCalledOnce()
    expect(result.current.micFallback).toBe(true)
    expect(result.current.micError).toBeNull()
  })

  it('clears the fallback note once a different microphone is selected', async () => {
    const stream = makeMockStream()
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(async (constraints) => {
      const audio = (constraints as MediaStreamConstraints).audio as MediaTrackConstraints
      if (audio.deviceId) throw new DOMException('Device gone', 'OverconstrainedError')
      return stream
    })
    const { result, rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: { ...makeOpts('listening', 'auto'), deviceId: 'unplugged' },
    })
    await act(async () => {})
    expect(result.current.micFallback).toBe(true)

    rerender({ ...makeOpts('thinking', 'auto'), deviceId: '' })
    await act(async () => {})
    expect(result.current.micFallback).toBe(false)
  })

  it('ignores a fallback from a request superseded by a newer selection', async () => {
    const stream = makeMockStream()
    let rejectSlow!: (error: unknown) => void
    const slow = new Promise<MediaStream>((_, reject) => { rejectSlow = reject })
    vi.mocked(navigator.mediaDevices.getUserMedia).mockImplementation(async (constraints) => {
      const audio = (constraints as MediaStreamConstraints).audio as MediaTrackConstraints
      if (audio.deviceId) return slow
      return stream
    })
    const { result, rerender } = renderHook((opts) => useMicCapture(opts), {
      initialProps: { ...makeOpts('listening', 'auto'), deviceId: 'slow-mic' },
    })
    await act(async () => {})
    rerender({ ...makeOpts('listening', 'auto'), deviceId: '' })
    await act(async () => {})

    await act(async () => { rejectSlow(new DOMException('Device gone', 'OverconstrainedError')) })
    expect(result.current.micFallback).toBe(false)
  })

  it('reports no fallback when the selected microphone opens', async () => {
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'auto'), deviceId: 'usb-mic' }),
    )
    await act(async () => {})
    expect(result.current.micFallback).toBe(false)
  })

  it('still surfaces a permission error for a selected microphone', async () => {
    getUserMediaError = new DOMException('Permission denied', 'NotAllowedError')
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'auto'), deviceId: 'usb-mic' }),
    )
    await act(async () => {})
    expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledOnce()
    expect(result.current.micError).toContain('denied')
  })
})

// ─── Live partials: the growing utterance, resent about every second ────────────

describe('live partials', () => {
  const frame = () => new Float32Array(1536).fill(0.3)
  const speechFrame = () => lastVADCallbacks.onFrameProcessed?.({ isSpeech: 0.9, notSpeech: 0.1 }, frame())
  const wavBytes = (b64: string) => atob(b64).length

  it('auto mode sends the speech heard so far every second while the user speaks', async () => {
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), onPartial }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      speechFrame()
      vi.advanceTimersByTime(1000)
    })
    expect(onPartial).toHaveBeenCalledOnce()
    const first = wavBytes(onPartial.mock.calls[0][0] as string)

    act(() => {
      speechFrame()
      vi.advanceTimersByTime(1000)
    })
    expect(onPartial).toHaveBeenCalledTimes(2)
    expect(wavBytes(onPartial.mock.calls[1][0] as string)).toBeGreaterThan(first)
  })

  it('auto mode keeps earlier segments of the same answer in the partial', async () => {
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), onPartial }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(16000).fill(0.3))
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      vi.advanceTimersByTime(1000)
    })

    // 1 s segment + one 1536-sample frame, 16 kHz PCM16 mono, 44-byte header
    expect(wavBytes(onPartial.mock.calls[0][0] as string)).toBe(44 + (16000 + 1536) * 2)
  })

  it('sends nothing while nobody speaks or when the audio did not grow', async () => {
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), onPartial }))
    await act(async () => {})

    act(() => vi.advanceTimersByTime(3000))
    expect(onPartial).not.toHaveBeenCalled()

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      vi.advanceTimersByTime(3000)
    })
    expect(onPartial).toHaveBeenCalledOnce()
  })

  it('caps the partial at the last 30 seconds', async () => {
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), onPartial }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(16000 * 40).fill(0.3))
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      vi.advanceTimersByTime(1000)
    })

    expect(wavBytes(onPartial.mock.calls[0][0] as string)).toBe(44 + 16000 * 30 * 2)
  })

  it('sends partials of the next utterance after one that ended without speech', async () => {
    // review R3-partial-sentlength-stale: the interval outlives a discarded utterance
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto'), onPartial }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      lastVADCallbacks.onSpeechEnd?.(new Float32Array(16000 * 2)) // silence: discarded at finalize
      vi.advanceTimersByTime(1000)
    })
    expect(onPartial).toHaveBeenCalledOnce()
    act(() => vi.advanceTimersByTime(5000)) // the silence timer finalizes it as no speech
    onPartial.mockClear()

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      vi.advanceTimersByTime(1000)
    })
    expect(onPartial).toHaveBeenCalledOnce()
    expect(wavBytes(onPartial.mock.calls[0][0] as string)).toBe(44 + 1536 * 2)
  })

  it('stops sending partials once the answer is finalized', async () => {
    const onFinalize = vi.fn()
    const onPartial = vi.fn()
    renderHook(() => useMicCapture({ ...makeOpts('listening', 'auto', onFinalize), onPartial }))
    await act(async () => {})

    act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      lastVADCallbacks.onSpeechEnd?.(new Float32Array([0.3]))
      vi.advanceTimersByTime(3000)
    })
    expect(onFinalize).toHaveBeenCalledOnce()
    onPartial.mockClear()

    act(() => {
      speechFrame()
      vi.advanceTimersByTime(5000)
    })
    expect(onPartial).not.toHaveBeenCalled()
  })

  it('push-to-talk sends the held audio every second and stops on release', async () => {
    const onFinalize = vi.fn()
    const onPartial = vi.fn()
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk', onFinalize), onPartial }),
    )
    await act(async () => {})
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    const chunk = () => activeScriptProcessor!.onaudioprocess?.({
      inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.3) },
    })

    act(() => { chunk(); vi.advanceTimersByTime(1000) })
    expect(onPartial).toHaveBeenCalledOnce()
    act(() => { chunk(); vi.advanceTimersByTime(1000) })
    expect(onPartial).toHaveBeenCalledTimes(2)

    await act(async () => { result.current.onTalkingChange(false) })
    expect(onFinalize).toHaveBeenCalledOnce()
    onPartial.mockClear()
    act(() => vi.advanceTimersByTime(5000))
    expect(onPartial).not.toHaveBeenCalled()
  })

  it('works without an onPartial handler (the exam page)', async () => {
    renderHook(() => useMicCapture(makeOpts('listening', 'auto')))
    await act(async () => {})
    expect(() => act(() => {
      lastVADCallbacks.onSpeechStart?.()
      speechFrame()
      vi.advanceTimersByTime(2000)
    })).not.toThrow()
  })

  it('tells the page to drop the provisional text when a held key sent nothing', async () => {
    const onFinalize = vi.fn()
    const onPartialDiscard = vi.fn()
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk', onFinalize), onPartial: vi.fn(), onPartialDiscard }),
    )
    await act(async () => {})
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})

    await act(async () => { result.current.onTalkingChange(false) }) // released at once: too short

    expect(onFinalize).not.toHaveBeenCalled()
    expect(onPartialDiscard).toHaveBeenCalledOnce()
  })

  it('keeps the provisional text when the answer is sent, so the final replaces it', async () => {
    const onPartialDiscard = vi.fn()
    const { result } = renderHook(() =>
      useMicCapture({ ...makeOpts('listening', 'push-to-talk'), onPartial: vi.fn(), onPartialDiscard }),
    )
    await act(async () => {})
    act(() => result.current.onTalkingChange(true))
    await act(async () => {})
    act(() => {
      activeScriptProcessor!.onaudioprocess?.({ inputBuffer: { getChannelData: () => new Float32Array(4096).fill(0.3) } })
      vi.advanceTimersByTime(400)
    })

    await act(async () => { result.current.onTalkingChange(false) })

    expect(onPartialDiscard).not.toHaveBeenCalled()
  })
})
