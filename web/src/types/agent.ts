import type { ObjectState, PointTarget } from '@/types/scene'
import type {
  ConnectionStatus,
  ProtocolState,
  WalkthroughAction,
  WalkthroughData,
  WalkthroughMessage,
  WalkthroughStepInfo,
} from '@/types/exam'
import type { VoiceMessage, VoicesMessage } from '@/types/voice'

/** A slash command or skill the open session accepts as text; name has no leading slash. */
export interface AgentCommand {
  name: string
  description: string
  hint: string
}

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

/** The two modes of a project session; the server owns what each one means. */
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
  /** Whether the backend can switch modes (Claude Code yes); the server only lists those that can. */
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
  /** The session's slash commands and skills, listed once it is open (empty when it lists none). */
  | { type: 'agent_commands'; commands: AgentCommand[] }
  /** The session's timeline so far, sent after `agent_backends` to a page that connects to it again. */
  | { type: 'agent_history'; entries: Omit<TimelineEntry, 'id'>[] }
  | { type: 'agent_started'; backend: string; model: string; cwd: string; mode?: AgentMode }
  | { type: 'agent_switching'; mode: AgentMode }
  | { type: 'agent_mode_changed'; backend: string; model: string; cwd: string; mode: AgentMode }
  | { type: 'mode_switch_request'; mode: AgentMode; label: string }
  | { type: 'mode_switch_closed'; mode: AgentMode }
  | { type: 'mode_switch_failed'; mode: AgentMode }
  | { type: 'state'; state: ProtocolState }
  | { type: 'transcript'; text: string; final: boolean }
  /** A spoken turn sent for review: the text goes to the composer, not to the agent. */
  | { type: 'transcript_draft'; text: string }
  | { type: 'agent_text'; text: string }
  | { type: 'agent_tool'; tool: string; summary: string }
  | { type: 'agent_reply'; text: string }
  | { type: 'agent_error'; message: string }
  | { type: 'permission_request'; id: string; tool: string; title: string; detail: string }
  | { type: 'permission_closed'; id: string }
  | { type: 'tts_audio'; format: string; data: string; step?: WalkthroughStepInfo & { seq: number }; text?: string }
  | { type: 'notice'; text: string }
  | WalkthroughMessage
  /** The agent finished with the scene (after the oral check): the page releases it if it ended. */
  | { type: 'walkthrough_cleared' }
  /** The agent points at objects of the finished scene while it asks about them; empty removes it. */
  | { type: 'walkthrough_point'; targets: PointTarget[] }
  /** The real outcome of a prediction: one object's new state on the finished scene, animated like a step. */
  | { type: 'walkthrough_result'; object: string; state: ObjectState }
  | VoicesMessage

// Page -> server messages on /ws/agent
export type AgentClientMessage =
  | { type: 'agent_hello' }
  | { type: 'pick_folder' }
  | { type: 'start_agent'; backend: string; model: string; cwd: string; mode?: AgentMode }
  | { type: 'switch_mode'; mode: AgentMode }
  | { type: 'mode_switch_response'; mode: AgentMode; allow: boolean }
  | { type: 'turn_audio'; format: 'wav'; data: string; review?: boolean }
  /** The whole utterance so far, resent about every second while the user speaks. */
  | { type: 'turn_audio_partial'; format: 'wav'; data: string }
  | { type: 'turn_text'; text: string }
  | { type: 'permission_response'; id: string; allow: boolean }
  | { type: 'interrupt' }
  | { type: 'playback_done'; seq?: number }
  | { type: 'walkthrough_control'; action: WalkthroughAction }
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
  /** What Whisper hears of the utterance still being spoken; provisional, never sent. */
  liveTranscript: string | null
  /** The mode being switched to while the handoff runs; null otherwise. */
  switching: AgentMode | null
  modeRequest: ModeSwitchRequest | null
  /**
   * A narrated scene the mentor or exam agent is playing; once it ends it stays until the agent
   * clears it, another scene starts or a reply brings code.
   */
  walkthrough: WalkthroughData | null
  /** The reply clip that is playing now (its source text), so the page can highlight it. */
  spoken: SpokenClip | null
  nextEntryId: number
}

export interface SpokenClip {
  id: number
  text: string
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
  /** The utterance ended without being sent (too short, silent or cancelled). */
  | { type: 'live_transcript_discarded' }
  /** A reply clip began playing. */
  | { type: 'speech_started'; id: number; text: string }
  /** A clip ended (``id``), or all speech stopped (no ``id``). */
  | { type: 'speech_ended'; id?: number }
