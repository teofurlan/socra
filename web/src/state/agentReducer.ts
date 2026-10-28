import { AGENT_MODES, type AgentAction, type AgentMode, type AgentState, type TimelineEntry } from '@/types/agent'
import { reduceWalkthrough } from '@/state/walkthroughReducer'

export const initialAgentState: AgentState = {
  connectionStatus: 'connecting',
  protocolState: 'idle',
  backends: [],
  defaultSelection: null,
  folder: null,
  pickingFolder: false,
  session: null,
  timeline: [],
  permissions: [],
  notice: null,
  switching: null,
  modeRequest: null,
  walkthrough: null,
  nextEntryId: 1,
}

const modeLabel = (mode: AgentMode) => AGENT_MODES.find((m) => m.id === mode)?.label ?? mode

/** A new user turn after a scene ended clears it; while it plays, what the user says steers it. */
function userTurn(state: AgentState, text: string): AgentState {
  const next = append(state, { kind: 'user', text })
  return state.walkthrough?.status === 'ended' ? { ...next, walkthrough: null } : next
}

function append(state: AgentState, entry: Omit<TimelineEntry, 'id'>): AgentState {
  return {
    ...state,
    timeline: [...state.timeline, { ...entry, id: state.nextEntryId }],
    nextEntryId: state.nextEntryId + 1,
  }
}

export function agentReducer(state: AgentState, action: AgentAction): AgentState {
  switch (action.type) {
    case 'agent_backends': {
      const next = { ...state, backends: action.backends, defaultSelection: action.default }
      if (action.session === undefined) return next
      if (action.session === null) {
        // The server no longer runs the conversation this page shows (it restarted).
        return state.session ? { ...next, session: null, permissions: [] } : next
      }
      const mode = action.session.mode ?? 'agent'
      const same =
        state.session?.backend === action.session.backend &&
        state.session.model === action.session.model &&
        state.session.cwd === action.session.cwd
      // The server dropped any switch request or handoff of the page that went away.
      const settled = { ...next, switching: null, modeRequest: null }
      return same && state.session
        ? { ...settled, session: { ...state.session, mode } }
        : {
            ...settled,
            session: { ...action.session, mode },
            folder: action.session.cwd,
            timeline: [],
            permissions: [],
          }
    }
    case 'agent_folder':
      // A cancelled dialog (null) keeps the folder already chosen.
      return { ...state, pickingFolder: false, folder: action.path ?? state.folder }
    case 'set_folder':
      return { ...state, folder: action.path }
    case 'folder_pick_requested':
      return { ...state, pickingFolder: true }
    case 'agent_started':
      return {
        ...state,
        session: { backend: action.backend, model: action.model, cwd: action.cwd, mode: action.mode ?? 'agent' },
        folder: action.cwd,
        switching: null,
        modeRequest: null,
        // Keep the optimistic first turn; the server accepts startup before it drains that turn.
        timeline: state.timeline.at(-1)?.kind === 'user' ? state.timeline.slice(-1) : [],
        permissions: [],
      }
    case 'agent_switching':
      return { ...state, switching: action.mode }
    case 'agent_mode_changed':
      // Same conversation on screen: the timeline stays and only gains the marker.
      return append(
        {
          ...state,
          session: { backend: action.backend, model: action.model, cwd: action.cwd, mode: action.mode },
          folder: action.cwd,
          switching: null,
          modeRequest: null,
        },
        { kind: 'handoff', text: `Context condensed · ${modeLabel(action.mode)}` },
      )
    case 'mode_switch_request':
      return { ...state, modeRequest: { mode: action.mode, label: action.label } }
    case 'mode_switch_answered':
      return { ...state, modeRequest: null }
    case 'mode_switch_closed':
      return state.modeRequest?.mode === action.mode ? { ...state, modeRequest: null } : state
    case 'mode_switch_failed':
      return { ...state, switching: null }
    case 'state':
      return { ...state, protocolState: action.state }
    case 'transcript':
      return action.final ? userTurn(state, action.text) : state
    case 'user_text':
      return userTurn(state, action.text)
    case 'walkthrough':
    case 'walkthrough_step':
    case 'walkthrough_status': {
      const walkthrough = reduceWalkthrough(state.walkthrough, action)
      return walkthrough === state.walkthrough ? state : { ...state, walkthrough }
    }
    case 'agent_text':
      return append(state, { kind: 'text', text: action.text })
    case 'agent_tool':
      return append(state, { kind: 'tool', text: action.summary, tool: action.tool })
    case 'agent_reply': {
      // The final text block usually arrives twice: as agent_text, then as the reply.
      const last = state.timeline.at(-1)
      if (last?.kind === 'text' && last.text === action.text) {
        return { ...state, timeline: [...state.timeline.slice(0, -1), { ...last, kind: 'reply' }] }
      }
      return append(state, { kind: 'reply', text: action.text })
    }
    case 'agent_error':
      return append(state, { kind: 'error', text: action.message })
    case 'permission_request':
      if (state.permissions.some((prompt) => prompt.id === action.id)) return state
      return {
        ...state,
        permissions: [
          ...state.permissions,
          { id: action.id, tool: action.tool, title: action.title, detail: action.detail },
        ],
      }
    case 'permission_answered':
    case 'permission_closed':
      return { ...state, permissions: state.permissions.filter((prompt) => prompt.id !== action.id) }
    case 'notice':
      return { ...state, notice: action.text }
    case 'clear_notice':
      return { ...state, notice: null }
    case 'set_status':
      // The server denies pending prompts when the page goes away; drop them here too.
      return action.status === 'connected'
        ? { ...state, connectionStatus: action.status }
        : { ...state, connectionStatus: action.status, permissions: [], modeRequest: null, switching: null }
    default:
      return state
  }
}
