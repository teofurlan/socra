import { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import { wasReplaced } from '@/lib/replacedPage'
import { PINNED_ATTEMPTS, pinnedToServer, socketUrl } from '@/lib/socketUrl'
import type { AgentClientMessage, AgentMode, AgentSelection, AgentServerMessage } from '@/types/agent'
import type { WalkthroughAction } from '@/types/exam'
import { EMPTY_VOICE_CATALOG, type VoiceCatalog } from '@/types/voice'
import { agentReducer, initialAgentState } from '@/state/agentReducer'
import { getStoredVoice, setStoredVoice } from '@/lib/storage'
import { useExamAudio } from './useExamAudio'

const NOTICE_MS = 4000
const FIRST_BACKOFF_MS = 500
const MAX_BACKOFF_MS = 5000

interface UseAgentSocketOptions {
  url?: string
}

/**
 * Agent-mode connection. Unlike the exam socket there is no mock fallback:
 * a missing server shows as reconnecting, and the hook keeps retrying, except
 * on a page pinned to one server's port (?ws=), which gives up once it is gone.
 */
export function useAgentSocket({ url = socketUrl('/ws/agent') }: UseAgentSocketOptions = {}) {
  const [state, dispatch] = useReducer(agentReducer, initialAgentState)
  const [listeningEpoch, setListeningEpoch] = useState(0)
  const [voices, setVoices] = useState<VoiceCatalog>(EMPTY_VOICE_CATALOG)
  const socketRef = useRef<WebSocket | null>(null)
  const noticeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { playAudio, stopAudio, getOutputVolume } = useExamAudio()

  const send = useCallback((message: AgentClientMessage) => {
    const socket = socketRef.current
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify(message))
    }
  }, [])

  const pickFolder = useCallback(() => {
    dispatch({ type: 'folder_pick_requested' })
    send({ type: 'pick_folder' })
  }, [send])

  const start = useCallback((selection: AgentSelection, cwd: string, mode?: AgentMode) => {
    send({
      type: 'start_agent', backend: selection.backend, model: selection.model, cwd,
      ...(mode ? { mode } : {}),
    })
  }, [send])

  const switchMode = useCallback((mode: AgentMode) => {
    send({ type: 'switch_mode', mode })
  }, [send])

  const answerModeSwitch = useCallback((mode: AgentMode, allow: boolean) => {
    dispatch({ type: 'mode_switch_answered' })
    send({ type: 'mode_switch_response', mode, allow })
  }, [send])

  const sendText = useCallback((text: string) => {
    dispatch({ type: 'user_text', text })
    send({ type: 'turn_text', text })
  }, [send])

  const sendAudio = useCallback((base64: string) => {
    send({ type: 'turn_audio', format: 'wav', data: base64 })
  }, [send])

  const answerPermission = useCallback((id: string, allow: boolean) => {
    dispatch({ type: 'permission_answered', id })
    send({ type: 'permission_response', id, allow })
  }, [send])

  const interrupt = useCallback(() => {
    send({ type: 'interrupt' })
    stopAudio()
  }, [send, stopAudio])

  /** Pause, repeat, go back, skip or stop a scene; the clip in the air is silenced at once. */
  const controlWalkthrough = useCallback((action: WalkthroughAction) => {
    send({ type: 'walkthrough_control', action })
    stopAudio()
  }, [send, stopAudio])

  const setVoice = useCallback(
    (id: string) => {
      setStoredVoice(id)
      setVoices((prev) => ({ ...prev, current: id }))
      send({ type: 'voice', voice: id })
    },
    [send]
  )

  useEffect(() => {
    let socket: WebSocket | null = null
    let disposed = false
    let backoffMs = FIRST_BACKOFF_MS
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
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
      backoffMs = Math.min(MAX_BACKOFF_MS, backoffMs * 2)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, delay)
    }

    const handle = (message: AgentServerMessage) => {
      if (message.type === 'voices') {
        setVoices({ voices: message.voices, current: message.current })
        return
      }
      if (message.type === 'tts_audio') {
        const step = message.step
        const done = () => send(step ? { type: 'playback_done', seq: step.seq } : { type: 'playback_done' })
        // A scene step replaces whatever clip is still playing; its picture changes when its sound begins.
        if (step) stopAudio()
        const onStart = step
          ? () => dispatch({ type: 'walkthrough_step', index: step.index, total: step.total, id: step.id, say: step.say, state: step.state })
          : undefined
        if (message.format === 'wav') playAudio(message.data, done, onStart)
        else done()
        return
      }
      if (message.type === 'walkthrough_status' && message.status !== 'playing') stopAudio()
      if (message.type === 'state' && message.state === 'listening') {
        setListeningEpoch((epoch) => epoch + 1)
      }
      if (message.type === 'notice') {
        if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current)
        noticeTimerRef.current = setTimeout(() => dispatch({ type: 'clear_notice' }), NOTICE_MS)
      }
      dispatch(message)
    }

    const connect = () => {
      if (disposed) return
      try {
        socket = new WebSocket(url)
      } catch {
        scheduleReconnect()
        return
      }
      socketRef.current = socket
      socket.onopen = () => {
        if (disposed) return
        backoffMs = FIRST_BACKOFF_MS
        failures = 0
        dispatch({ type: 'set_status', status: 'connected' })
        send({ type: 'agent_hello' })
        const storedVoice = getStoredVoice()
        send(storedVoice ? { type: 'voice', voice: storedVoice } : { type: 'voice' })
      }
      socket.onmessage = (event) => {
        if (disposed) return
        let message: unknown
        try {
          message = JSON.parse(event.data)
        } catch {
          console.error('Ignoring a malformed agent message:', event.data)
          return
        }
        if (typeof message !== 'object' || message === null || typeof (message as { type?: unknown }).type !== 'string') {
          console.error('Ignoring an agent message without a type:', message)
          return
        }
        handle(message as AgentServerMessage)
      }
      socket.onclose = (event) => {
        if (disposed) return
        if (wasReplaced(event)) dispatch({ type: 'set_status', status: 'replaced' })
        else scheduleReconnect()
      }
    }

    connect()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (noticeTimerRef.current) clearTimeout(noticeTimerRef.current)
      if (socket) {
        socket.onopen = null
        socket.onmessage = null
        socket.onclose = null
        socket.close()
      }
      socketRef.current = null
    }
  }, [url, send, playAudio, stopAudio])

  return {
    state,
    dispatch,
    listeningEpoch,
    getOutputVolume,
    pickFolder,
    start,
    switchMode,
    answerModeSwitch,
    sendText,
    sendAudio,
    answerPermission,
    interrupt,
    controlWalkthrough,
    voices,
    setVoice,
  }
}
