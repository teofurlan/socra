import type { ConnectionStatus, ProtocolState } from '@/types/exam'
import type { VoiceMessage, VoicesMessage } from '@/types/voice'

/** What the user picks and the page persists: a backend and one of its models. */
export interface AgentSelection {
  backend: string
  model: string
}

export interface AgentModelOption {
  id: string
  label: string
}

export type BackendState = 'ready' | 'not_configured' | 'unreachable'

/** The three modes of a project session; the server owns what each one means. */
export type AgentMode = 'agent' | 'mentor' | 'exam'

export const AGENT_MODES: readonly { id: AgentMode; label: string }[] = [
  { id: 'agent', label: 'Agent' },
  { id: 'mentor', label: 'Mentor' },
  { id: 'exam', label: 'Exam' },
]

export interface AgentBackendInfo {
  id: string
  label: string
  models: AgentModelOption[]
  status: { state: BackendState; message: string }
  /** Whether the backend can switch modes (Claude Code yes, Pi not yet). */
  supports_modes?: boolean
}

export interface AgentSession extends AgentSelection {
  cwd: string
  mode: AgentMode
}

/** A mode switch the agent asked for by voice; the user confirms it on screen. */
export interface ModeSwitchRequest {
  mode: AgentMode
  label: string
}

export interface PermissionPrompt {
  id: string
  tool: string
  title: string
  detail: string
}

export type TimelineKind = 'user' | 'text' | 'tool' | 'reply' | 'error' | 'handoff'

export interface TimelineEntry {
  id: number
  kind: TimelineKind
  text: string
  /** Tool name, only for `tool` entries. */
  tool?: string
}

// Server -> page messages on /ws/agent
export type AgentServerMessage =
  | {
      type: 'agent_backends'
      backends: AgentBackendInfo[]
      default: AgentSelection | null
      /** The conversation the server holds now; the page resyncs to it on every connect. */
      session?: (AgentSelection & { cwd: string; mode?: AgentMode }) | null
    }
  | { type: 'agent_folder'; path: string | null }
  | { type: 'agent_started'; backend: string; model: string; cwd: string; mode?: AgentMode }
  | { type: 'agent_switching'; mode: AgentMode }
  | { type: 'agent_mode_changed'; backend: string; model: string; cwd: string; mode: AgentMode }
  | { type: 'mode_switch_request'; mode: AgentMode; label: string }
  | { type: 'mode_switch_closed'; mode: AgentMode }
  | { type: 'mode_switch_failed'; mode: AgentMode }
  | { type: 'state'; state: ProtocolState }
  | { type: 'transcript'; text: string; final: boolean }
  | { type: 'agent_text'; text: string }
  | { type: 'agent_tool'; tool: string; summary: string }
  | { type: 'agent_reply'; text: string }
  | { type: 'agent_error'; message: string }
  | { type: 'permission_request'; id: string; tool: string; title: string; detail: string }
  | { type: 'permission_closed'; id: string }
  | { type: 'tts_audio'; format: string; data: string }
  | { type: 'notice'; text: string }
  | VoicesMessage

// Page -> server messages on /ws/agent
export type AgentClientMessage =
  | { type: 'agent_hello' }
  | { type: 'pick_folder' }
  | { type: 'start_agent'; backend: string; model: string; cwd: string; mode?: AgentMode }
  | { type: 'switch_mode'; mode: AgentMode }
  | { type: 'mode_switch_response'; mode: AgentMode; allow: boolean }
  | { type: 'turn_audio'; format: 'wav'; data: string }
  | { type: 'turn_text'; text: string }
  | { type: 'permission_response'; id: string; allow: boolean }
  | { type: 'interrupt' }
  | { type: 'playback_done' }
  | VoiceMessage

export interface AgentState {
  connectionStatus: ConnectionStatus
  protocolState: ProtocolState
  backends: AgentBackendInfo[]
  defaultSelection: AgentSelection | null
  folder: string | null
  pickingFolder: boolean
  session: AgentSession | null
  timeline: TimelineEntry[]
  permissions: PermissionPrompt[]
  notice: string | null
  /** The mode being switched to while the handoff runs; null otherwise. */
  switching: AgentMode | null
  modeRequest: ModeSwitchRequest | null
  nextEntryId: number
}

export type AgentAction =
  | AgentServerMessage
  | { type: 'set_status'; status: ConnectionStatus }
  | { type: 'set_folder'; path: string | null }
  | { type: 'folder_pick_requested' }
  | { type: 'user_text'; text: string }
  | { type: 'permission_answered'; id: string }
  | { type: 'mode_switch_answered' }
  | { type: 'clear_notice' }
