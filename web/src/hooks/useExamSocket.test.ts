import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useExamSocket } from './useExamSocket'
import { STORAGE_KEY_MODE, STORAGE_KEY_VOICE } from '@/lib/storage'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  readyState: number = 0
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  })

  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  simulateOpen() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  simulateError() {
    this.onerror?.(new Event('error'))
  }

  sent(): unknown[] {
    return this.send.mock.calls.map(([raw]) => JSON.parse(raw as string))
  }
}

class MockAudioSource {
  buffer: AudioBuffer | null = null
  connect = vi.fn()
  disconnect = vi.fn()
  start = vi.fn()
  stop = vi.fn()
  onended: (() => void) | null = null
}

class MockAudioContext {
  static instances: MockAudioContext[] = []
  state = 'running'
  currentTime = 2
  destination = {}
  resume = vi.fn(async () => {})
  close = vi.fn(async () => {})
  decodeAudioData = vi.fn(async (_data: ArrayBuffer) => ({ duration: 0.25 } as AudioBuffer))
  analyser = {
    fftSize: 256,
    connect: vi.fn(),
    disconnect: vi.fn(),
    getByteTimeDomainData: vi.fn((data: Uint8Array) => data.fill(160)),
  }
  sources: MockAudioSource[] = []
  createAnalyser = vi.fn(() => this.analyser)
  createBufferSource() {
    const source = new MockAudioSource()
    this.sources.push(source)
    return source
  }
  constructor() { MockAudioContext.instances.push(this) }
}

describe('useExamSocket', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    window.localStorage.clear()
    MockWebSocket.instances = []
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
    vi.useFakeTimers()
    MockAudioContext.instances = []
    vi.stubGlobal('AudioContext', MockAudioContext)
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('connects to WebSocket and sends initial mode on open', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))

    expect(MockWebSocket.instances.length).toBe(1)
    expect(MockWebSocket.instances[0].url).toBe('ws://localhost:8766/ws')
    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    expect(result.current.state.connectionStatus).toBe('connected')
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'mode', mode: 'auto' }))
    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'voice' }))
  })

  it('sends {"type":"reanswer"} when reanswer is triggered', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      result.current.reanswer()
    })

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'reanswer' }))
    expect(result.current.state.protocolState).toBe('listening')
  })

  it('persists mode change and sends {"type":"mode", ...}', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      result.current.setMode('push-to-talk')
    })

    expect(result.current.state.mode).toBe('push-to-talk')
    expect(window.localStorage.getItem(STORAGE_KEY_MODE)).toBe('push-to-talk')
    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'mode', mode: 'push-to-talk' })
    )
  })

  it('updates state when receiving server messages', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateOpen()
    })

    // Question message
    act(() => {
      ws.simulateMessage({
        type: 'question',
        index: 1,
        total: 5,
        text: 'What is a semaphore?',
      })
    })

    expect(result.current.state.question).toEqual({
      index: 1,
      total: 5,
      text: 'What is a semaphore?',
    })

    // State message
    act(() => {
      ws.simulateMessage({
        type: 'state',
        state: 'speaking',
      })
    })
    expect(result.current.state.protocolState).toBe('speaking')

    // Transcript message
    act(() => {
      ws.simulateMessage({
        type: 'transcript',
        text: 'A semaphore is a synchronization primitive...',
        final: true,
      })
    })
    expect(result.current.state.transcript).toEqual({
      text: 'A semaphore is a synchronization primitive...',
      final: true,
    })
  })

  it('plays protocol WAV audio in order, exposes its volume, and releases audio/socket resources', async () => {
    const { result, unmount } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())
    await act(async () => {
      ws.simulateMessage({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
      ws.simulateMessage({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
    })
    expect(MockAudioContext.instances).toHaveLength(1)
    const audio = MockAudioContext.instances[0]
    expect([...new Uint8Array(audio.decodeAudioData.mock.calls[0][0])]).toEqual([82, 73, 70, 70])
    expect(audio.sources).toHaveLength(2)
    expect(audio.sources[0].connect).toHaveBeenCalledWith(audio.analyser)
    expect(audio.analyser.connect).toHaveBeenCalledWith(audio.destination)
    expect(audio.sources[0].start).toHaveBeenCalledWith(2)
    expect(audio.sources[1].start).toHaveBeenCalledWith(2.25)
    expect(result.current.getOutputVolume()).toBeGreaterThan(0)
    unmount()
    for (const source of audio.sources) {
      expect(source.stop).toHaveBeenCalledOnce()
      expect(source.disconnect).toHaveBeenCalledOnce()
    }
    expect(audio.analyser.disconnect).toHaveBeenCalledOnce()
    expect(audio.close).toHaveBeenCalledOnce()
    expect(ws.close).toHaveBeenCalledOnce()
  })

  it('does not start audio after unmount while decoding', async () => {
    const { unmount } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())
    let finishDecode!: (buffer: AudioBuffer) => void
    vi.spyOn(MockAudioContext.prototype, 'createBufferSource')
    // Instantiate audio with one message, then hold its decode at the browser boundary.
    const decode = vi.fn(() => new Promise<AudioBuffer>((resolve) => { finishDecode = resolve }))
    // A context is created lazily by the incoming message.
    const OriginalContext = MockAudioContext
    vi.stubGlobal('AudioContext', class extends OriginalContext {
      constructor() { super(); this.decodeAudioData = decode }
    })
    await act(async () => ws.simulateMessage({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' }))
    expect(decode).toHaveBeenCalledOnce()
    unmount()
    await act(async () => finishDecode({ duration: 1 } as AudioBuffer))
    expect(MockAudioContext.prototype.createBufferSource).not.toHaveBeenCalled()
    expect(MockAudioContext.instances[0].close).toHaveBeenCalledOnce()
  })

  it('sends answer audio using the exact protocol envelope', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())
    act(() => result.current.sendAudio('UklGRg=='))
    expect(ws.send).toHaveBeenLastCalledWith('{"type":"answer_audio","format":"wav","data":"UklGRg=="}')
  })

  it('ignores late events from a socket disposed by a connection change', () => {
    const { result, rerender, unmount } = renderHook(
      ({ url }) => useExamSocket({ forceMock: false, url }),
      { initialProps: { url: 'ws://localhost:8766/ws' } },
    )
    rerender({ url: 'ws://localhost:8767/ws' })
    const [old, current] = MockWebSocket.instances
    act(() => current.simulateOpen())
    act(() => old.simulateError())
    expect(result.current.state.connectionStatus).toBe('connected')
    act(() => vi.advanceTimersByTime(10000))
    expect(result.current.state.question).toBeNull()
    unmount()
    expect(current.close).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('stops the mock driver when switching to a real connection', () => {
    const { result, rerender, unmount } = renderHook(
      ({ forceMock }) => useExamSocket({ forceMock }), { initialProps: { forceMock: true } },
    )
    rerender({ forceMock: false })
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())
    act(() => result.current.reanswer())
    act(() => vi.advanceTimersByTime(10000))
    expect(result.current.state.connectionStatus).toBe('connected')
    expect(result.current.state.transcript.text).toBe('')
    expect(ws.send).toHaveBeenLastCalledWith('{"type":"reanswer"}')
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })

  it('cancels the mock cycle on unmount', () => {
    const { result, unmount } = renderHook(() => useExamSocket({ forceMock: true }))
    act(() => vi.advanceTimersByTime(1500))
    expect(result.current.state.protocolState).toBe('speaking')
    unmount()
    expect(vi.getTimerCount()).toBe(0)
    expect(MockWebSocket.instances).toHaveLength(0)
  })

  it('falls back to mock driver on connection failure', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]

    act(() => {
      ws.simulateError()
    })

    expect(result.current.state.connectionStatus).toBe('mock')
    expect(result.current.state.protocolState).toBe('thinking')

    // Advance time for thinking -> question + speaking (3s)
    act(() => {
      vi.advanceTimersByTime(1500)
    })

    expect(result.current.state.protocolState).toBe('speaking')
    expect(result.current.state.question).not.toBeNull()
  })

  it('sends playback_done on audio end', async () => {
    renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    await act(async () => {
      ws.simulateMessage({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
    })

    const audio = MockAudioContext.instances[0]
    expect(audio.sources).toHaveLength(1)
    const source = audio.sources[0]

    act(() => {
      source.onended?.()
    })

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'playback_done' }))
  })

  it('sends playback_done on audio play error', async () => {
    const OriginalContext = MockAudioContext
    vi.stubGlobal('AudioContext', class extends OriginalContext {
      constructor() {
        super()
        this.decodeAudioData = vi.fn(async () => {
          throw new Error('decode failed')
        })
      }
    })

    renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    await act(async () => {
      ws.simulateMessage({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
    })

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'playback_done' }))
  })

  it('stays closed when a newer exam page takes over, instead of taking it back', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    act(() => {
      ws.onclose?.(new CloseEvent('close', { code: 1000, reason: 'Replaced by a new page' }))
    })
    expect(result.current.state.connectionStatus).toBe('replaced')

    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    expect(MockWebSocket.instances).toHaveLength(1)
    expect(result.current.state.connectionStatus).toBe('replaced')
  })

  it('reconnects with backoff (0.5s doubling to 5s) when socket closes mid-exam', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws1 = MockWebSocket.instances[0]
    act(() => ws1.simulateOpen())
    expect(result.current.state.connectionStatus).toBe('connected')

    // Close socket mid-exam (not finished)
    act(() => {
      ws1.close()
    })
    expect(result.current.state.connectionStatus).toBe('reconnecting')
    expect(MockWebSocket.instances).toHaveLength(1)

    // Advance 500ms (0.5s) -> first reconnect
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(MockWebSocket.instances).toHaveLength(2)
    const ws2 = MockWebSocket.instances[1]

    // ws2 fails/closes
    act(() => {
      ws2.close()
    })
    expect(result.current.state.connectionStatus).toBe('reconnecting')

    // Advance 500ms -> should not reconnect yet because backoff doubled to 1000ms
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(MockWebSocket.instances).toHaveLength(2)

    // Advance another 500ms (1000ms total) -> second reconnect
    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(MockWebSocket.instances).toHaveLength(3)
    const ws3 = MockWebSocket.instances[2]

    // ws3 fails/closes -> next backoff should be 2000ms
    act(() => {
      ws3.close()
    })
    act(() => {
      vi.advanceTimersByTime(1999)
    })
    expect(MockWebSocket.instances).toHaveLength(3)
    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(MockWebSocket.instances).toHaveLength(4)
  })

  it('stops reconnecting after finished is received', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateOpen())

    // Receive finished message
    act(() => {
      ws.simulateMessage({ type: 'finished' })
    })

    // Now close socket
    act(() => {
      ws.close()
    })

    expect(result.current.state.connectionStatus).toBe('disconnected')
    // Advance timers by 10s
    act(() => {
      vi.advanceTimersByTime(10000)
    })
    // No new WebSocket instances should be created
    expect(MockWebSocket.instances).toHaveLength(1)
  })

  it('sends { type: "voice" } on open with nothing stored', () => {
    renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.simulateOpen()
    })
    expect(ws.sent()).toEqual([{ type: 'mode', mode: 'auto' }, { type: 'voice' }])
  })

  it('sends { type: "voice", voice: "dora" } on open when dora is stored', () => {
    window.localStorage.setItem(STORAGE_KEY_VOICE, 'dora')
    renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.simulateOpen()
    })
    expect(ws.sent()).toEqual([{ type: 'mode', mode: 'auto' }, { type: 'voice', voice: 'dora' }])
  })

  it('updates voices when receiving a voices message', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.simulateOpen()
    })
    expect(result.current.voices).toEqual({ voices: [], current: null })

    act(() => {
      ws.simulateMessage({
        type: 'voices',
        voices: [
          { id: 'alex-dora', label: 'Alex 75% + Dora 25%' },
          { id: 'santa', label: 'Santa' },
        ],
        current: 'alex-dora',
      })
    })

    expect(result.current.voices).toEqual({
      voices: [
        { id: 'alex-dora', label: 'Alex 75% + Dora 25%' },
        { id: 'santa', label: 'Santa' },
      ],
      current: 'alex-dora',
    })
  })

  it('setVoice stores in localStorage, sends voice message, and updates current optimistically', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: false }))
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.simulateOpen()
    })

    act(() => {
      result.current.setVoice('santa')
    })

    expect(window.localStorage.getItem(STORAGE_KEY_VOICE)).toBe('santa')
    expect(ws.sent()).toContainEqual({ type: 'voice', voice: 'santa' })
    expect(result.current.voices.current).toBe('santa')
  })

  it('setVoice only stores and updates local state in mock mode', () => {
    const { result } = renderHook(() => useExamSocket({ forceMock: true }))

    act(() => {
      result.current.setVoice('santa')
    })

    expect(window.localStorage.getItem(STORAGE_KEY_VOICE)).toBe('santa')
    expect(result.current.voices.current).toBe('santa')
    expect(MockWebSocket.instances).toHaveLength(0)
  })
  it('on a page pinned to its server with ?ws, gives up instead of mocking or retrying forever', () => {
    window.history.replaceState(null, '', '/?ws=51001')
    try {
      const { result } = renderHook(() => useExamSocket({ forceMock: false }))
      expect(MockWebSocket.instances[0].url).toBe('ws://localhost:51001/ws')

      act(() => MockWebSocket.instances[0].simulateError())
      act(() => MockWebSocket.instances[0].close())
      expect(result.current.state.connectionStatus).toBe('reconnecting')

      for (let attempt = 1; attempt < 5; attempt++) {
        act(() => vi.advanceTimersByTime(5000))
        act(() => MockWebSocket.instances[MockWebSocket.instances.length - 1].close())
      }
      expect(result.current.state.connectionStatus).toBe('gone')

      const count = MockWebSocket.instances.length
      act(() => vi.advanceTimersByTime(60_000))
      expect(MockWebSocket.instances).toHaveLength(count)
      expect(result.current.state.connectionStatus).toBe('gone')
    } finally {
      window.history.replaceState(null, '', '/')
    }
  })

  describe('walkthrough', () => {
    const stepClip = (index: number, seq: number, lines: [number, number] | null = [index, index]) => ({
      type: 'tts_audio',
      format: 'wav',
      data: 'UklGRg==',
      step: { index, total: 2, id: `s${index}`, say: `Step ${index}.`, state: { code: { visible: true, lines } }, seq },
    })

    const open = () => {
      const hook = renderHook(() => useExamSocket({ forceMock: false }))
      const ws = MockWebSocket.instances[0]
      act(() => ws.simulateOpen())
      act(() => ws.simulateMessage({ type: 'walkthrough', title: 'Two', objects: [{ id: 'code', primitive: 'code', params: { code: 'a\nb', language: '' }, hidden: false }], total: 2 }))
      return { ...hook, ws }
    }

    it('focuses a step only once its audio starts playing', async () => {
      let release: (buffer: AudioBuffer) => void = () => {}
      vi.stubGlobal('AudioContext', class extends MockAudioContext {
        constructor() {
          super()
          this.decodeAudioData = vi.fn(() => new Promise<AudioBuffer>((resolve) => { release = resolve }))
        }
      })
      const { result, ws } = open()

      await act(async () => ws.simulateMessage(stepClip(1, 7)))
      expect(result.current.state.walkthrough?.step).toBeNull()

      await act(async () => {
        release({ duration: 0.25 } as AudioBuffer)
        for (let i = 0; i < 5; i++) await Promise.resolve()
      })
      expect(result.current.state.walkthrough?.step).toEqual({ index: 1, total: 2, id: 's1', say: 'Step 1.', state: { code: { visible: true, lines: [1, 1] } } })
    })

    it('reports the clip it finished with its sequence number', async () => {
      const { ws } = open()
      await act(async () => ws.simulateMessage(stepClip(1, 7)))

      act(() => MockAudioContext.instances[0].sources[0].onended?.())

      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'playback_done', seq: 7 }))
    })

    it('a new step silences the clip still playing', async () => {
      const { ws } = open()
      await act(async () => ws.simulateMessage(stepClip(1, 7)))
      const first = MockAudioContext.instances[0].sources[0]

      await act(async () => ws.simulateMessage(stepClip(2, 8)))

      expect(first.stop).toHaveBeenCalled()
      expect(MockAudioContext.instances[0].sources).toHaveLength(2)
    })

    it('controls stop the audio and are sent to the server', async () => {
      const { result, ws } = open()
      await act(async () => ws.simulateMessage(stepClip(1, 7)))
      const source = MockAudioContext.instances[0].sources[0]

      act(() => result.current.controlWalkthrough('pause'))

      expect(source.stop).toHaveBeenCalled()
      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'walkthrough_control', action: 'pause' }))
    })

    it.each(['pause', 'repeat', 'back', 'next', 'stop'] as const)('sends %s before the stopped clip reports playback_done', async (action) => {
      const { result, ws } = open()
      await act(async () => ws.simulateMessage(stepClip(1, 7)))
      const source = MockAudioContext.instances[0].sources[0]
      ws.send.mockClear()

      act(() => result.current.controlWalkthrough(action))

      expect(ws.sent()).toEqual([
        { type: 'walkthrough_control', action },
        { type: 'playback_done', seq: 7 },
      ])
      expect(source.stop).toHaveBeenCalledOnce()
    })

    it('a paused status from the server silences the audio', async () => {
      const { ws } = open()
      await act(async () => ws.simulateMessage(stepClip(1, 7)))
      const source = MockAudioContext.instances[0].sources[0]

      act(() => ws.simulateMessage({ type: 'walkthrough_status', status: 'paused' }))

      expect(source.stop).toHaveBeenCalled()
    })
  })
})
