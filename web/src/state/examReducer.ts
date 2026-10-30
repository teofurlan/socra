import type { ExamState, ProtocolState, ServerMessage, TurnMode, ConnectionStatus } from '@/types/exam'
import { reduceWalkthrough } from '@/state/walkthroughReducer'

export type ExamAction =
  | ServerMessage
  | { type: 'set_mode'; mode: TurnMode }
  | { type: 'set_status'; status: ConnectionStatus }
  | { type: 'reanswer' }
  | { type: 'reset_transcript' }
  | { type: 'clear_notice' }

export const initialExamState: ExamState = {
  connectionStatus: 'connecting',
  protocolState: 'idle',
  question: null,
  finished: false,
  transcript: {
    text: '',
    final: false,
  },
  mode: 'auto',
  notice: null,
  walkthrough: null,
}

export function examReducer(state: ExamState, action: ExamAction): ExamState {
  switch (action.type) {
    case 'state':
      return {
        ...state,
        protocolState: action.state as ProtocolState,
      }

    case 'question':
      return {
        ...state,
        question: {
          index: action.index,
          total: action.total,
          text: action.text,
          ...(action.code !== undefined ? { code: action.code } : {}),
        },
        finished: false,
        transcript: {
          text: '',
          final: false,
        },
        notice: null,
        walkthrough: null,
      }

    case 'finished':
      return {
        ...state,
        protocolState: 'idle',
        question: null,
        transcript: { text: '', final: false },
        finished: true,
        notice: null,
        walkthrough: null,
      }

    case 'notice':
      return {
        ...state,
        notice: action.text,
      }

    case 'clear_notice':
      return {
        ...state,
        notice: null,
      }

    case 'transcript':
      return {
        ...state,
        transcript: {
          text: action.text,
          final: action.final,
        },
      }

    case 'walkthrough':
    case 'walkthrough_step':
    case 'walkthrough_status': {
      const walkthrough = reduceWalkthrough(state.walkthrough, action)
      return walkthrough === state.walkthrough ? state : { ...state, walkthrough }
    }

    case 'tts_audio':
      return state

    case 'set_mode':
      return {
        ...state,
        mode: action.mode,
      }

    case 'set_status':
      return {
        ...state,
        connectionStatus: action.status,
      }

    case 'reanswer':
      return {
        ...state,
        transcript: {
          text: '',
          final: false,
        },
        protocolState: 'listening',
      }

    case 'reset_transcript':
      return {
        ...state,
        transcript: {
          text: '',
          final: false,
        },
      }

    default:
      return state
  }
}
