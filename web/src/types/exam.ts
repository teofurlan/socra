import type { SceneObject, SceneState } from '@/types/scene'
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

/** The step a narrated scene is on, with every object's state while it speaks. */
export interface WalkthroughStepInfo {
  index: number
  total: number
  id: string
  say: string
  state: SceneState
}

export type WalkthroughStatus = 'playing' | 'paused' | 'ended'
export type WalkthroughAction = 'pause' | 'resume' | 'repeat' | 'back' | 'next' | 'stop'

/** A narrated scene playing on the page (explain() is a scene with one code object). */
export interface WalkthroughData {
  title: string
  objects: SceneObject[]
  total: number
  step: WalkthroughStepInfo | null
  status: WalkthroughStatus
  /** Why it ended: completed, stopped, disconnected or error. */
  reason: string | null
}

/** The messages that drive a narrated scene, on the exam and the agent page alike. */
export type WalkthroughMessage =
  | { type: 'walkthrough'; title: string; objects: SceneObject[]; total: number }
  | ({ type: 'walkthrough_step' } & WalkthroughStepInfo)
  | { type: 'walkthrough_status'; status: WalkthroughStatus; reason?: string }

// Server -> Client messages
export type ServerMessage =
  | { type: 'state'; state: ProtocolState }
  | { type: 'question'; index: number; total: number; text: string; code?: string }
  | { type: 'finished' }
  | { type: 'tts_audio'; format: string; data: string; step?: WalkthroughStepInfo & { seq: number } }
  | WalkthroughMessage
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
