import type { VoiceMessage, VoicesMessage } from '@/types/voice'

export type ProtocolState = 'idle' | 'speaking' | 'listening' | 'thinking'

export type TurnMode = 'auto' | 'push-to-talk'

/** `replaced`: a newer Socra page took over the server connection; this one stays closed. */
export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'mock' | 'reconnecting' | 'replaced' | 'gone'

export interface QuestionData {
  index: number
  total: number
  text: string
  code?: string
}

export interface TranscriptData {
  text: string
  final: boolean
}

/** The step a walkthrough is on; ``lines`` is 1-based and inclusive, null when nothing is highlighted. */
export interface WalkthroughStepInfo {
  index: number
  total: number
  say: string
  lines: [number, number] | null
}

export type WalkthroughStatus = 'playing' | 'paused' | 'ended'
export type WalkthroughAction = 'pause' | 'resume' | 'repeat' | 'back' | 'next' | 'stop'

export interface WalkthroughData {
  code: string
  language: string
  total: number
  step: WalkthroughStepInfo | null
  status: WalkthroughStatus
  /** Why it ended: completed, stopped, disconnected or error. */
  reason: string | null
}

// Server -> Client messages
export type ServerMessage =
  | { type: 'state'; state: ProtocolState }
  | { type: 'question'; index: number; total: number; text: string; code?: string }
  | { type: 'finished' }
  | { type: 'tts_audio'; format: string; data: string; step?: WalkthroughStepInfo & { seq: number } }
  | { type: 'walkthrough'; code: string; language: string; total: number }
  | ({ type: 'walkthrough_step' } & WalkthroughStepInfo)
  | { type: 'walkthrough_status'; status: WalkthroughStatus; reason?: string }
  | { type: 'transcript'; text: string; final: boolean }
  | { type: 'notice'; text: string }
  | VoicesMessage

// Client -> Server messages
export type ClientMessage =
  | { type: 'answer_audio'; format: string; data: string }
  | { type: 'answer_text'; text: string }
  | { type: 'reanswer' }
  | { type: 'mode'; mode: TurnMode }
  | { type: 'playback_done'; seq?: number }
  | { type: 'walkthrough_control'; action: WalkthroughAction }
  | VoiceMessage

export interface ExamState {
  connectionStatus: ConnectionStatus
  protocolState: ProtocolState
  question: QuestionData | null
  finished: boolean
  transcript: TranscriptData
  mode: TurnMode
  notice: string | null
  walkthrough: WalkthroughData | null
}
