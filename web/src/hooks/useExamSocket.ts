import { useEffect, useReducer, useRef, useCallback, useState } from 'react'
import { wasReplaced } from '@/lib/replacedPage'
import { PINNED_ATTEMPTS, pinnedToServer, socketUrl } from '@/lib/socketUrl'
import type {
  ClientMessage,
  ServerMessage,
  TurnMode,
  WalkthroughAction,
} from '@/types/exam'
import { EMPTY_VOICE_CATALOG, type VoiceCatalog } from '@/types/voice'
import { examReducer, initialExamState } from '@/state/examReducer'
import { getStoredTurnMode, setStoredTurnMode, getStoredVoice, setStoredVoice } from '@/lib/storage'
import { useExamAudio } from './useExamAudio'

const MOCK_QUESTIONS: { text: string; code?: string; partialAnswer: string; finalAnswer: string }[] = [
  {
    text: 'What is the fundamental difference between a process and a thread in modern operating systems?',
    partialAnswer: 'A process is an execution environment with its own memory space...',
    finalAnswer:
      'A process is an execution environment with its own dedicated virtual memory space, whereas threads are lightweight execution units within a process that share the same address space and resources.',
  },
  {
    text: 'This handler retries a failed request. What happens when the server is down for a minute?',
    code: [
      'async function fetchWithRetry(url: string, attempt = 0): Promise<Response> {',
      '  try {',
      '    return await fetch(url)',
      '  } catch (error) {',
      '    if (attempt >= 5) throw error',
      '    const delay = 500 * 2 ** attempt',
      '    await new Promise((resolve) => setTimeout(resolve, delay))',
      '    return fetchWithRetry(url, attempt + 1)',
      '  }',
      '}',
    ].join('\n'),
    partialAnswer: 'It retries with exponential backoff...',
    finalAnswer:
      'It retries five times with exponential backoff, waiting about fifteen seconds in total, and then throws, so a one-minute outage still fails.',
  },
  {
    text: 'How does virtual memory protect memory isolation between different user processes?',
    partialAnswer: 'Virtual memory maps virtual addresses to physical pages using page tables...',
    finalAnswer:
      'Virtual memory assigns each process its own page table managed by the OS and hardware MMU. Addresses are translated dynamically, preventing a process from accessing physical memory pages mapped to another process.',
  },
  {
    text: 'Explain the three-way handshake used to establish a TCP connection.',
    partialAnswer: 'The client sends SYN, the server responds with SYN-ACK...',
    finalAnswer:
      'The client sends a SYN packet with an initial sequence number. The server responds with a SYN-ACK packet acknowledging the client sequence number and proposing its own. Finally, the client sends an ACK packet back, establishing the bidirectional connection.',
  },
]

export interface UseExamSocketOptions {
  url?: string
  forceMock?: boolean
}

export function useExamSocket(options: UseExamSocketOptions = {}) {
  const { url = socketUrl('/ws'), forceMock } = options
  const { playAudio, stopAudio, getOutputVolume } = useExamAudio()
  const [state, dispatch] = useReducer(examReducer, {
    ...initialExamState,
    mode: getStoredTurnMode('auto'),
  })

  // Re-answer can deliver listening -> listening; the state string alone is not a turn identity.
  const [listeningEpoch, setListeningEpoch] = useState(0)
  const [voices, setVoices] = useState<VoiceCatalog>(EMPTY_VOICE_CATALOG)
  const socketRef = useRef<WebSocket | null>(null)
  const mockTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isMockActiveRef = useRef<boolean>(false)
  const currentQuestionIdxRef = useRef<number>(0)
  const unmountedRef = useRef<boolean>(false)
  const noticeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const clearMockTimers = useCallback(() => {
    if (mockTimerRef.current) {
      clearTimeout(mockTimerRef.current)
      mockTimerRef.current = null
    }
  }, [])

  const startMockDriver = useCallback(() => {
    if (unmountedRef.current) return
    isMockActiveRef.current = true
    clearMockTimers()
    dispatch({ type: 'set_status', status: 'mock' })

    const runMockCycle = () => {
      if (!isMockActiveRef.current || unmountedRef.current) return

      const total = MOCK_QUESTIONS.length
      const qIndex = (currentQuestionIdxRef.current % total) + 1
      const qData = MOCK_QUESTIONS[qIndex - 1]

      // Step 1: Thinking (1.5s)
      dispatch({ type: 'state', state: 'thinking' })

      mockTimerRef.current = setTimeout(() => {
        if (!isMockActiveRef.current || unmountedRef.current) return

        // Step 2: Emit question & change state to speaking (3s)
        dispatch({
          type: 'question',
          index: qIndex,
          total,
          text: qData.text,
          ...(qData.code ? { code: qData.code } : {}),
        })
        dispatch({ type: 'state', state: 'speaking' })

        // 3s speaking duration
        mockTimerRef.current = setTimeout(() => {
          if (!isMockActiveRef.current || unmountedRef.current) return

          // Step 3: Listening
          dispatch({ type: 'state', state: 'listening' })

          // Step 4: Fake partial transcript after 1.5s
          mockTimerRef.current = setTimeout(() => {
            if (!isMockActiveRef.current || unmountedRef.current) return

            dispatch({
              type: 'transcript',
              text: qData.partialAnswer,
              final: false,
            })

            // Step 5: Fake final transcript after 1.5s
            mockTimerRef.current = setTimeout(() => {
              if (!isMockActiveRef.current || unmountedRef.current) return

              dispatch({
                type: 'transcript',
                text: qData.finalAnswer,
                final: true,
              })

              // Step 6: Wait 3s before advancing to next question
              mockTimerRef.current = setTimeout(() => {
                if (!isMockActiveRef.current || unmountedRef.current) return
                currentQuestionIdxRef.current += 1
                runMockCycle()
              }, 3000)
            }, 1500)
          }, 1500)
        }, 3000)
      }, 1500)
    }

    runMockCycle()
  }, [clearMockTimers])

  const send = useCallback((message: ClientMessage) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(message))
    }
  }, [])

  const setMode = useCallback(
    (newMode: TurnMode) => {
      setStoredTurnMode(newMode)
      dispatch({ type: 'set_mode', mode: newMode })
      send({ type: 'mode', mode: newMode })
    },
    [send]
  )

  const setVoice = useCallback(
    (id: string) => {
      setStoredVoice(id)
      setVoices((prev) => ({ ...prev, current: id }))
      send({ type: 'voice', voice: id })
    },
    [send]
  )

  const reanswer = useCallback(() => {
    dispatch({ type: 'reanswer' })
    send({ type: 'reanswer' })

    // If mock driver is active, simulate listening for an answer again
    if (isMockActiveRef.current) {
      setListeningEpoch((epoch) => epoch + 1)
      clearMockTimers()
      const total = MOCK_QUESTIONS.length
      const qIndex = (currentQuestionIdxRef.current % total) + 1
      const qData = MOCK_QUESTIONS[qIndex - 1]

      mockTimerRef.current = setTimeout(() => {
        if (!isMockActiveRef.current || unmountedRef.current) return
        dispatch({
          type: 'transcript',
          text: qData.partialAnswer,
          final: false,
        })

        mockTimerRef.current = setTimeout(() => {
          if (!isMockActiveRef.current || unmountedRef.current) return
          dispatch({
            type: 'transcript',
            text: qData.finalAnswer,
            final: true,
          })

          mockTimerRef.current = setTimeout(() => {
            if (!isMockActiveRef.current || unmountedRef.current) return
            currentQuestionIdxRef.current += 1
            startMockDriver()
          }, 3000)
        }, 1500)
      }, 1500)
    }
  }, [send, clearMockTimers, startMockDriver])

  /** A typed answer is final as typed; the server echoes it back as the transcript. */
  const sendText = useCallback(
    (text: string) => {
      if (isMockActiveRef.current) {
        clearMockTimers()
        dispatch({ type: 'transcript', text, final: true })
        mockTimerRef.current = setTimeout(() => {
          if (!isMockActiveRef.current || unmountedRef.current) return
          currentQuestionIdxRef.current += 1
          startMockDriver()
        }, 2000)
        return
      }
      send({ type: 'answer_text', text })
    },
    [send, clearMockTimers, startMockDriver]
  )

  /** Pause, repeat, go back, skip or stop the walkthrough; the clip in the air is silenced at once. */
  const controlWalkthrough = useCallback(
    (action: WalkthroughAction) => {
      stopAudio()
      send({ type: 'walkthrough_control', action })
    },
    [send, stopAudio]
  )

  const sendAudio = useCallback(
    (base64Data: string) => {
      send({ type: 'answer_audio', format: 'wav', data: base64Data })
    },
    [send]
  )

  useEffect(() => {
    unmountedRef.current = false

    const isExplicitMock =
      forceMock ??
      (typeof window !== 'undefined' &&
        new URLSearchParams(window.location.search).get('mock') === '1')

    if (isExplicitMock) {
      startMockDriver()
      return () => {
        unmountedRef.current = true
        isMockActiveRef.current = false
        clearMockTimers()
      }
    }

    let socket: WebSocket | null = null
    let hasConnected = false
    let disposed = false
    let fellBack = false
    let backoffMs = 500
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    const finishedRef = { current: false }

    const detachSocket = () => {
      if (!socket) return
      socket.onopen = null
      socket.onmessage = null
      socket.onerror = null
      socket.onclose = null
    }
    const fallBack = () => {
      if (disposed || fellBack) return
      fellBack = true
      detachSocket()
      socket?.close()
      socketRef.current = null
      startMockDriver()
    }

    // A page pinned to one server's port (?ws=) has nothing to mock or wait for
    // once that server is gone: it retries a few times, then says so.
    const pinned = pinnedToServer(url)
    let failures = 0
    const scheduleReconnect = () => {
      failures += 1
      if (pinned && failures >= PINNED_ATTEMPTS) {
        dispatch({ type: 'set_status', status: 'gone' })
        return
      }
      dispatch({ type: 'set_status', status: 'reconnecting' })
      const delay = backoffMs
      backoffMs = Math.min(5000, backoffMs * 2)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connectSocket()
      }, delay)
    }

    const connectSocket = () => {
      if (disposed || fellBack || finishedRef.current) return

      try {
        socket = new WebSocket(url)
        socketRef.current = socket

        socket.onopen = () => {
          if (disposed || fellBack) return
          hasConnected = true
          backoffMs = 500
          failures = 0
          dispatch({ type: 'set_status', status: 'connected' })
          const currentMode = getStoredTurnMode('auto')
          socket?.send(JSON.stringify({ type: 'mode', mode: currentMode }))
          const storedVoice = getStoredVoice()
          const voiceMsg: ClientMessage = storedVoice
            ? { type: 'voice', voice: storedVoice }
            : { type: 'voice' }
          socket?.send(JSON.stringify(voiceMsg))
        }

        socket.onmessage = (event) => {
          if (disposed || fellBack) return
          try {
            const data = JSON.parse(event.data) as ServerMessage
            if (data.type === 'voices') {
              setVoices({ voices: data.voices, current: data.current })
              return
            }
            if (data.type === 'finished') {
              finishedRef.current = true
            } else if (data.type === 'question') {
              finishedRef.current = false
            }

            if (data.type === 'tts_audio') {
              const step = data.step
              const done = () => send(step ? { type: 'playback_done', seq: step.seq } : { type: 'playback_done' })
              // A walkthrough step replaces whatever clip is still playing; its focus lands when its sound begins.
              if (step) stopAudio()
              if (data.format === 'wav') {
                const focus = step
                  ? () => dispatch({ type: 'walkthrough_step', index: step.index, total: step.total, say: step.say, lines: step.lines })
                  : undefined
                playAudio(data.data, done, focus)
              } else {
                done()
              }
            } else {
              if (data.type === 'walkthrough_status' && data.status !== 'playing') stopAudio()
              if (data.type === 'state' && data.state === 'listening') {
                setListeningEpoch((epoch) => epoch + 1)
              }
              if (data.type === 'notice') {
                if (noticeTimeoutRef.current) clearTimeout(noticeTimeoutRef.current)
                noticeTimeoutRef.current = setTimeout(() => {
                  dispatch({ type: 'clear_notice' })
                }, 4000)
              }
              dispatch(data)
            }
          } catch (err) {
            console.error('Failed to parse WebSocket message:', err)
          }
        }

        socket.onerror = () => {
          if (!disposed && !hasConnected && !pinned) fallBack()
        }

        socket.onclose = (event) => {
          if (disposed || fellBack) return
          if (wasReplaced(event)) {
            dispatch({ type: 'set_status', status: 'replaced' })
          } else if (!hasConnected && !pinned) {
            fallBack()
          } else if (finishedRef.current) {
            dispatch({ type: 'set_status', status: 'disconnected' })
          } else {
            scheduleReconnect()
          }
        }
      } catch {
        if (!hasConnected && !pinned) {
          fallBack()
        } else if (!finishedRef.current) {
          scheduleReconnect()
        }
      }
    }

    connectSocket()

    return () => {
      disposed = true
      unmountedRef.current = true
      isMockActiveRef.current = false
      clearMockTimers()
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (noticeTimeoutRef.current) clearTimeout(noticeTimeoutRef.current)
      detachSocket()
      if (!fellBack) socket?.close()
      socketRef.current = null
    }
  }, [url, forceMock, startMockDriver, clearMockTimers, playAudio, stopAudio])

  return {
    state,
    setMode,
    reanswer,
    sendText,
    sendAudio,
    controlWalkthrough,
    getOutputVolume,
    listeningEpoch,
    dispatch,
    voices,
    setVoice,
  }
}
