import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useAgentSocket } from './useAgentSocket'
import { FakeAudioContext, FakeWebSocket } from '@/test/fakeSocket'
import { STORAGE_KEY_VOICE } from '@/lib/storage'

describe('useAgentSocket', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    window.localStorage.clear()
    FakeWebSocket.instances = []
    FakeAudioContext.instances = []
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket
    vi.stubGlobal('AudioContext', FakeAudioContext)
    vi.useFakeTimers()
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  const connected = () => {
    const hook = renderHook(() => useAgentSocket())
    const ws = FakeWebSocket.latest()
    act(() => ws.open())
    return { ...hook, ws }
  }

  it('connects to the agent route and says hello', () => {
    const { result, ws } = connected()

    expect(ws.url).toBe('ws://localhost:8766/ws/agent')
    expect(result.current.state.connectionStatus).toBe('connected')
    expect(ws.sent()).toEqual([{ type: 'agent_hello' }, { type: 'voice' }])
  })

  it('connects to the WebSocket port the server put in the page URL', () => {
    window.history.replaceState(null, '', '/?ws=51001&mode=agent')
    try {
      renderHook(() => useAgentSocket())
      expect(FakeWebSocket.latest().url).toBe('ws://localhost:51001/ws/agent')
    } finally {
      window.history.replaceState(null, '', '/')
    }
  })

  it('sends every page action in the agent protocol', () => {
    const { result, ws } = connected()

    act(() => {
      result.current.pickFolder()
      result.current.start({ backend: 'claude-code', model: 'opus' }, 'C:\\work')
      result.current.sendText('list the files')
      result.current.sendAudio('UklGRg==')
      result.current.answerPermission('r1', true)
      result.current.interrupt()
    })

    expect(ws.sent().slice(2)).toEqual([
      { type: 'pick_folder' },
      { type: 'start_agent', backend: 'claude-code', model: 'opus', cwd: 'C:\\work' },
      { type: 'turn_text', text: 'list the files' },
      { type: 'turn_audio', format: 'wav', data: 'UklGRg==' },
      { type: 'permission_response', id: 'r1', allow: true },
      { type: 'interrupt' },
    ])
  })

  it('sends mode switches and answers to a voice-requested switch', () => {
    const { result, ws } = connected()
    act(() => ws.receive({ type: 'mode_switch_request', mode: 'exam', label: 'Exam' }))
    expect(result.current.state.modeRequest).toEqual({ mode: 'exam', label: 'Exam' })

    act(() => {
      result.current.switchMode('mentor')
      result.current.answerModeSwitch('exam', true)
    })

    expect(ws.sent().slice(2)).toEqual([
      { type: 'switch_mode', mode: 'mentor' },
      { type: 'mode_switch_response', mode: 'exam', allow: true },
    ])
    expect(result.current.state.modeRequest).toBeNull()
  })

  it('starts a session in the chosen mode', () => {
    const { result, ws } = connected()

    act(() => result.current.start({ backend: 'claude-code', model: 'opus' }, 'C:\\work', 'exam'))

    expect(ws.sent().at(-1)).toEqual({
      type: 'start_agent', backend: 'claude-code', model: 'opus', cwd: 'C:\\work', mode: 'exam',
    })
  })

  it('shows typed turns in the timeline and marks folder picks and answered prompts', () => {
    const { result, ws } = connected()
    act(() => ws.receive({ type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run', detail: '' }))

    act(() => {
      result.current.sendText('hello')
      result.current.pickFolder()
      result.current.answerPermission('r1', false)
    })

    expect(result.current.state.timeline.at(-1)).toMatchObject({ kind: 'user', text: 'hello' })
    expect(result.current.state.pickingFolder).toBe(true)
    expect(result.current.state.permissions).toEqual([])
  })

  it('feeds server messages to the state', () => {
    const { result, ws } = connected()

    act(() => {
      ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'opus', cwd: 'C:\\work' })
      ws.receive({ type: 'agent_reply', text: 'Done.' })
    })

    expect(result.current.state.session?.cwd).toBe('C:\\work')
    expect(result.current.state.timeline.at(-1)).toMatchObject({ kind: 'reply', text: 'Done.' })
  })

  it('ignores malformed messages', () => {
    const { result, ws } = connected()
    const before = result.current.state

    act(() => {
      ws.onmessage?.(new MessageEvent('message', { data: 'not json' }))
      ws.receive([1, 2])
      ws.receive({ no: 'type' })
    })

    expect(result.current.state).toBe(before)
  })

  it('counts each listening phase so mic capture can re-arm', () => {
    const { result, ws } = connected()
    const start = result.current.listeningEpoch

    act(() => {
      ws.receive({ type: 'state', state: 'listening' })
      ws.receive({ type: 'state', state: 'thinking' })
      ws.receive({ type: 'state', state: 'listening' })
    })

    expect(result.current.listeningEpoch).toBe(start + 2)
  })

  it('plays speech and reports playback_done when the clip ends', async () => {
    const { ws } = connected()

    await act(async () => {
      ws.receive({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
      await vi.runAllTimersAsync()
    })
    const source = FakeAudioContext.latest().sources[0]
    act(() => source.onended?.())

    expect(ws.sent()).toContainEqual({ type: 'playback_done' })
  })

  it('interrupting stops the speech that is playing', async () => {
    const { result, ws } = connected()
    await act(async () => {
      ws.receive({ type: 'tts_audio', format: 'wav', data: 'UklGRg==' })
      await vi.runAllTimersAsync()
    })
    const source = FakeAudioContext.latest().sources[0]

    act(() => result.current.interrupt())

    expect(source.stop).toHaveBeenCalled()
    expect(ws.sent()).toContainEqual({ type: 'playback_done' })
  })

  it('clears a notice after a few seconds', () => {
    const { result, ws } = connected()

    act(() => ws.receive({ type: 'notice', text: 'Wait for the reply.' }))
    expect(result.current.state.notice).toBe('Wait for the reply.')

    act(() => vi.advanceTimersByTime(4000))
    expect(result.current.state.notice).toBeNull()
  })

  it('keeps retrying with backoff, also before the first connection', () => {
    const { result } = renderHook(() => useAgentSocket())

    act(() => FakeWebSocket.latest().drop())
    expect(result.current.state.connectionStatus).toBe('reconnecting')
    expect(FakeWebSocket.instances).toHaveLength(1)

    act(() => vi.advanceTimersByTime(500))
    expect(FakeWebSocket.instances).toHaveLength(2)

    act(() => FakeWebSocket.latest().drop())
    act(() => vi.advanceTimersByTime(999))
    expect(FakeWebSocket.instances).toHaveLength(2)
    act(() => vi.advanceTimersByTime(1))
    expect(FakeWebSocket.instances).toHaveLength(3)

    act(() => FakeWebSocket.latest().open())
    expect(result.current.state.connectionStatus).toBe('connected')
    expect(FakeWebSocket.latest().sent()).toEqual([{ type: 'agent_hello' }, { type: 'voice' }])
  })

  it('on a page pinned to its server with ?ws, gives up once that server is gone', () => {
    window.history.replaceState(null, '', '/?ws=51001&mode=agent')
    try {
      const { result } = renderHook(() => useAgentSocket())
      act(() => FakeWebSocket.latest().open())
      act(() => FakeWebSocket.latest().drop())

      for (let attempt = 1; attempt < 5; attempt++) {
        act(() => vi.advanceTimersByTime(5000))
        act(() => FakeWebSocket.latest().drop())
      }
      expect(result.current.state.connectionStatus).toBe('gone')

      const count = FakeWebSocket.instances.length
      act(() => vi.advanceTimersByTime(60_000))
      expect(FakeWebSocket.instances).toHaveLength(count)
    } finally {
      window.history.replaceState(null, '', '/')
    }
  })

  it('stays closed when a newer page takes over, instead of taking it back', () => {
    const { result, ws } = connected()

    act(() => ws.drop({ code: 1000, reason: 'Replaced by a new page' }))
    expect(result.current.state.connectionStatus).toBe('replaced')

    act(() => vi.advanceTimersByTime(30_000))
    expect(FakeWebSocket.instances).toHaveLength(1)
    expect(result.current.state.connectionStatus).toBe('replaced')
  })

  it('stops reconnecting after unmount', () => {
    const { unmount } = renderHook(() => useAgentSocket())
    const ws = FakeWebSocket.latest()

    unmount()
    act(() => vi.advanceTimersByTime(10_000))

    expect(ws.close).toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('sends { type: "voice" } on open with nothing stored', () => {
    const { ws } = connected()
    expect(ws.sent()).toEqual([{ type: 'agent_hello' }, { type: 'voice' }])
  })

  it('sends { type: "voice", voice: "dora" } on open when dora is stored', () => {
    window.localStorage.setItem(STORAGE_KEY_VOICE, 'dora')
    const { ws } = connected()
    expect(ws.sent()).toEqual([{ type: 'agent_hello' }, { type: 'voice', voice: 'dora' }])
  })

  it('updates voices when receiving a voices message', () => {
    const { result, ws } = connected()
    expect(result.current.voices).toEqual({ voices: [], current: null })

    act(() => {
      ws.receive({
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
    const { result, ws } = connected()

    act(() => {
      result.current.setVoice('santa')
    })

    expect(window.localStorage.getItem(STORAGE_KEY_VOICE)).toBe('santa')
    expect(ws.sent()).toContainEqual({ type: 'voice', voice: 'santa' })
    expect(result.current.voices.current).toBe('santa')
  })
})

