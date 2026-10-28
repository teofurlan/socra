import { describe, it, expect } from 'vitest'
import { agentReducer, initialAgentState } from './agentReducer'
import type { AgentAction, AgentState } from '@/types/agent'

const run = (...actions: AgentAction[]): AgentState => actions.reduce(agentReducer, initialAgentState)

const backends = {
  type: 'agent_backends',
  backends: [
    {
      id: 'claude-code',
      label: 'Claude Code',
      models: [{ id: 'sonnet', label: 'Sonnet' }],
      status: { state: 'ready', message: '' },
    },
  ],
  default: { backend: 'claude-code', model: 'sonnet' },
  session: null,
} as const satisfies AgentAction

const started = {
  type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work',
} as const satisfies AgentAction

describe('agentReducer', () => {
  it('starts disconnected from any agent, with nothing selected', () => {
    expect(initialAgentState.connectionStatus).toBe('connecting')
    expect(initialAgentState.protocolState).toBe('idle')
    expect(initialAgentState.session).toBeNull()
    expect(initialAgentState.timeline).toEqual([])
    expect(initialAgentState.permissions).toEqual([])
  })

  it('keeps the queued first user turn when the accepted startup arrives', () => {
    const withTurn = agentReducer(initialAgentState, { type: 'user_text', text: 'list the files' })

    const startedState = agentReducer(withTurn, started)

    expect(startedState.timeline).toEqual(withTurn.timeline)
    expect(startedState.session).toEqual({ backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work', mode: 'mentor' })
  })

  it('stores the backends and the server default', () => {
    const state = run(backends)

    expect(state.backends).toEqual(backends.backends)
    expect(state.defaultSelection).toEqual({ backend: 'claude-code', model: 'sonnet' })
  })

  it('tracks a folder pick and keeps the previous folder when the dialog is cancelled', () => {
    let state = run({ type: 'set_folder', path: 'C:\\old' }, { type: 'folder_pick_requested' })
    expect(state.pickingFolder).toBe(true)

    state = agentReducer(state, { type: 'agent_folder', path: null })
    expect(state.pickingFolder).toBe(false)
    expect(state.folder).toBe('C:\\old')

    state = agentReducer(state, { type: 'agent_folder', path: 'C:\\new' })
    expect(state.folder).toBe('C:\\new')
  })

  it('a started session clears the previous timeline and prompts', () => {
    const state = run(
      started,
      { type: 'agent_text', text: 'old' },
      { type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run', detail: '' },
      { ...started, model: 'opus' },
    )

    expect(state.session).toEqual({ backend: 'claude-code', model: 'opus', cwd: 'C:\\work', mode: 'mentor' })
    expect(state.timeline).toEqual([])
    expect(state.permissions).toEqual([])
  })

  it('builds the timeline from the user turn, tools and the reply', () => {
    const state = run(
      started,
      { type: 'transcript', text: 'what is here?', final: true },
      { type: 'agent_text', text: 'Let me look.' },
      { type: 'agent_tool', tool: 'Read', summary: 'app.py' },
      { type: 'agent_text', text: 'An exam app.' },
      { type: 'agent_reply', text: 'An exam app.' },
      { type: 'user_text', text: 'thanks' },
      { type: 'agent_error', message: 'Rate limited' },
    )

    expect(state.timeline.map(({ kind, text }) => [kind, text])).toEqual([
      ['user', 'what is here?'],
      ['text', 'Let me look.'],
      ['tool', 'app.py'],
      ['reply', 'An exam app.'],
      ['user', 'thanks'],
      ['error', 'Rate limited'],
    ])
    expect(state.timeline[2].tool).toBe('Read')
    expect(new Set(state.timeline.map((entry) => entry.id)).size).toBe(6)
  })

  it('a reply that differs from the last text is appended, not merged', () => {
    const state = run(started, { type: 'agent_text', text: 'Thinking.' }, { type: 'agent_reply', text: 'Done.' })

    expect(state.timeline.map((entry) => entry.kind)).toEqual(['text', 'reply'])
  })

  it('agent errors also show when no session is running yet', () => {
    const state = run({ type: 'agent_error', message: 'Folder not found: C:\\x' })

    expect(state.timeline).toEqual([expect.objectContaining({ kind: 'error', text: 'Folder not found: C:\\x' })])
  })

  it('queues permission prompts and removes them when answered or closed', () => {
    let state = run(
      started,
      { type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run git status', detail: 'git status' },
      { type: 'permission_request', id: 'r2', tool: 'Write', title: 'Write a file', detail: 'a.txt' },
      { type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run git status', detail: 'git status' },
    )
    expect(state.permissions.map((p) => p.id)).toEqual(['r1', 'r2'])

    state = agentReducer(state, { type: 'permission_answered', id: 'r1' })
    expect(state.permissions.map((p) => p.id)).toEqual(['r2'])

    state = agentReducer(state, { type: 'permission_closed', id: 'r2' })
    expect(state.permissions).toEqual([])
  })

  it('follows the protocol state, notices and connection status', () => {
    let state = run({ type: 'state', state: 'thinking' }, { type: 'notice', text: 'Wait' }, { type: 'set_status', status: 'connected' })
    expect(state.protocolState).toBe('thinking')
    expect(state.notice).toBe('Wait')
    expect(state.connectionStatus).toBe('connected')

    state = agentReducer(state, { type: 'clear_notice' })
    expect(state.notice).toBeNull()
  })

  it('a lost connection drops the prompts the server can no longer receive', () => {
    const state = run(
      started,
      { type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run', detail: '' },
      { type: 'set_status', status: 'reconnecting' },
    )

    expect(state.permissions).toEqual([])
  })

  it('a reconnect to a server without that session drops the stale session', () => {
    const state = run(
      started,
      { type: 'agent_reply', text: 'old' },
      { ...backends, session: null },
    )

    expect(state.session).toBeNull()
    expect(state.timeline.at(-1)).toMatchObject({ kind: 'reply', text: 'old' })
  })

  it('a reconnect to the same session keeps the conversation', () => {
    const state = run(
      started,
      { type: 'agent_reply', text: 'still here' },
      { ...backends, session: { backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work' } },
    )

    expect(state.session).toEqual({ backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work', mode: 'mentor' })
    expect(state.timeline).toHaveLength(1)
  })

  it('a page opened while the server runs a session joins it', () => {
    const state = run({ ...backends, session: { backend: 'claude-code', model: 'opus', cwd: 'D:\\app' } })

    expect(state.session).toEqual({ backend: 'claude-code', model: 'opus', cwd: 'D:\\app', mode: 'mentor' })
    expect(state.folder).toBe('D:\\app')
  })

  it('ignores unknown messages', () => {
    const unknown = { type: 'surprise' } as unknown as AgentAction

    expect(agentReducer(initialAgentState, unknown)).toBe(initialAgentState)
  })
})

describe('agentReducer mode switching', () => {
  const inExam = {
    type: 'agent_mode_changed', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work', mode: 'exam',
  } as const satisfies AgentAction

  it('starts in mentor mode with no switch or request pending', () => {
    expect(initialAgentState.switching).toBeNull()
    expect(initialAgentState.modeRequest).toBeNull()
    expect(run(started).session?.mode).toBe('mentor')
  })

  it('takes the mode a started session reports', () => {
    expect(run({ ...started, mode: 'mentor' }).session?.mode).toBe('mentor')
  })

  it('shows the target mode while the handoff runs', () => {
    expect(run(started, { type: 'agent_switching', mode: 'exam' }).switching).toBe('exam')
  })

  it('keeps the timeline across a switch and marks where the context was condensed', () => {
    const state = run(
      started,
      { type: 'user_text', text: 'add login' },
      { type: 'agent_reply', text: 'Done.' },
      { type: 'agent_switching', mode: 'exam' },
      inExam,
    )

    expect(state.session).toEqual({ backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work', mode: 'exam' })
    expect(state.switching).toBeNull()
    expect(state.timeline.map((entry) => entry.kind)).toEqual(['user', 'reply', 'handoff'])
    expect(state.timeline.at(-1)?.text).toBe('Context condensed · Exam')
  })

  it('keeps the page prompts that survive a switch and clears the pending request', () => {
    const state = run(
      started,
      { type: 'mode_switch_request', mode: 'exam', label: 'Exam' },
      { type: 'agent_switching', mode: 'exam' },
      inExam,
    )

    expect(state.modeRequest).toBeNull()
  })

  it('holds a voice-requested switch until it is answered or withdrawn', () => {
    const asked = run(started, { type: 'mode_switch_request', mode: 'exam', label: 'Exam' })
    expect(asked.modeRequest).toEqual({ mode: 'exam', label: 'Exam' })

    expect(agentReducer(asked, { type: 'mode_switch_answered' }).modeRequest).toBeNull()
    expect(agentReducer(asked, { type: 'mode_switch_closed', mode: 'exam' }).modeRequest).toBeNull()
    // A close for another mode does not clear the live request.
    expect(agentReducer(asked, { type: 'mode_switch_closed', mode: 'mentor' }).modeRequest).not.toBeNull()
  })

  it('a failed switch ends the switching state and stays in the old mode', () => {
    const state = run(started, { type: 'agent_switching', mode: 'exam' }, { type: 'mode_switch_failed', mode: 'mentor' })

    expect(state.switching).toBeNull()
    expect(state.session?.mode).toBe('mentor')
  })

  it('a reconnect to the same session adopts the server mode and drops pending switch state', () => {
    const state = run(
      started,
      { type: 'agent_reply', text: 'kept' },
      { type: 'mode_switch_request', mode: 'exam', label: 'Exam' },
      { ...backends, session: { backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work', mode: 'mentor' } },
    )

    expect(state.session?.mode).toBe('mentor')
    expect(state.modeRequest).toBeNull()
    expect(state.timeline).toHaveLength(1)
  })

  it('losing the connection drops a pending request and a running switch', () => {
    const state = run(
      started,
      { type: 'mode_switch_request', mode: 'exam', label: 'Exam' },
      { type: 'agent_switching', mode: 'exam' },
      { type: 'set_status', status: 'reconnecting' },
    )

    expect(state.modeRequest).toBeNull()
    expect(state.switching).toBeNull()
  })
})
