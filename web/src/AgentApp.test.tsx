import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AgentApp from './AgentApp'
import { FakeAudioContext, FakeWebSocket } from '@/test/fakeSocket'
import { STORAGE_KEY_AGENT_FOLDER, STORAGE_KEY_AGENT_SELECTION, STORAGE_KEY_VISUALIZER } from '@/lib/storage'

// Real capture needs a microphone and WebAudio; this page only wires it up.
const micOptions: { protocolState?: string; onFinalize?: (b64: string) => void } = {}
vi.mock('@/hooks/useMicCapture', () => ({
  useMicCapture: (options: { protocolState: string; onFinalize: (b64: string) => void }) => {
    Object.assign(micOptions, options)
    return {
      micError: null,
      micFallback: false,
      getInputVolume: () => 0,
      silenceCountdownMs: 0,
      onTalkingChange: () => {},
    }
  },
}))

const backends = {
  type: 'agent_backends',
  backends: [
    {
      id: 'claude-code',
      label: 'Claude Code',
      models: [{ id: 'sonnet', label: 'Sonnet' }, { id: 'opus', label: 'Opus' }],
      status: { state: 'ready', message: '' },
      supports_modes: true,
    },
    {
      id: 'pi',
      label: 'Pi',
      models: [{ id: 'anthropic/sonnet', label: 'Sonnet' }],
      status: { state: 'ready', message: '' },
      supports_modes: false,
    },
  ],
  default: { backend: 'claude-code', model: 'sonnet' },
}

describe('AgentApp', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    window.localStorage.clear()
    FakeWebSocket.instances = []
    FakeAudioContext.instances = []
    globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket
    vi.stubGlobal('AudioContext', FakeAudioContext)
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  const openPage = () => {
    const view = render(<AgentApp />)
    const ws = FakeWebSocket.latest()
    act(() => ws.open())
    act(() => ws.receive(backends))
    return { ...view, ws }
  }

  const startSession = (ws: FakeWebSocket) => {
    act(() => {
      ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'opus', cwd: 'C:\\work\\socra' })
      ws.receive({ type: 'state', state: 'listening' })
    })
  }

  it('keeps the voice stage outside the scrolling conversation', () => {
    openPage()
    const stage = document.querySelector('.voice-stage')!
    expect(stage.querySelector('[data-testid="orb-visualizer"]')).toBeInTheDocument()
    expect(stage.querySelector('[data-testid="state-label"]')).toBeInTheDocument()
    expect(stage.closest('.shell-scroll')).toBeNull()
  })

  it('restores the chosen model and folder after a reload', () => {
    window.localStorage.setItem(STORAGE_KEY_AGENT_SELECTION, JSON.stringify({ backend: 'claude-code', model: 'opus' }))
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')

    openPage()

    expect(document.querySelector('.shell > .background-pattern')).toHaveAttribute('aria-hidden', 'true')

    expect(screen.getByRole('button', { name: /agent and model/i })).toHaveTextContent('Opus')
    expect(screen.getByRole('button', { name: /choose another folder/i })).toHaveTextContent(/^socra$/)
  })

  it('opens directly into the conversation with folder and model controls in the composer dock', () => {
    openPage()

    expect(screen.getByRole('region', { name: /conversation/i })).toBeInTheDocument()
    expect(screen.getByTestId('timeline-empty')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Choose folder' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /agent and model/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /start agent/i })).toBeNull()
  })

  it('starts the selected agent before sending the first turn and keeps it visible while startup is pending', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()

    await user.type(screen.getByLabelText('Message the agent'), 'list the files{Enter}')

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' },
      { type: 'turn_text', text: 'list the files' },
    ])
    expect(screen.getByRole('list', { name: 'Conversation' })).toHaveTextContent('list the files')

    act(() => {
      ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' })
      ws.receive({ type: 'agent_error', message: 'The agent could not start.' })
      ws.receive({ ...backends, session: null })
    })
    expect(screen.getByRole('list', { name: 'Conversation' }).querySelectorAll('[data-kind="user"]')).toHaveLength(1)
    expect(screen.getByRole('list', { name: 'Conversation' })).toHaveTextContent('The agent could not start.')
  })

  it('keeps the typed message when agent choices are missing and explains what to choose', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()

    await user.type(screen.getByLabelText('Message the agent'), 'keep this prompt{Enter}')

    expect(screen.getByLabelText('Message the agent')).toHaveValue('keep this prompt')
    expect(screen.getAllByRole('status').some((item) => /choose a folder/i.test(item.textContent ?? ''))).toBe(true)
    expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'turn_text' }))
  })

  it('remembers a new model choice and the picked folder', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()

    await user.click(screen.getByRole('button', { name: /agent and model/i }))
    await user.click(screen.getByRole('option', { name: 'Opus' }))
    await user.click(screen.getByRole('button', { name: /choose folder/i }))
    act(() => ws.receive({ type: 'agent_folder', path: 'D:\\code\\app' }))

    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY_AGENT_SELECTION)!)).toEqual({ backend: 'claude-code', model: 'opus' })
    expect(window.localStorage.getItem(STORAGE_KEY_AGENT_FOLDER)).toBe('D:\\code\\app')
    expect(ws.sent()).toContainEqual({ type: 'pick_folder' })
  })

  it('starts the selected agent in the selected folder when the first prompt is sent', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()

    await user.type(screen.getByLabelText('Message the agent'), 'inspect the project{Enter}')

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' },
      { type: 'turn_text', text: 'inspect the project' },
    ])
    expect(screen.getByLabelText('Message the agent')).toHaveValue('')
  })

  it('shows the session in the existing conversation without a setup barrier', () => {
    const { ws } = openPage()

    startSession(ws)

    const session = screen.getByTestId('session-bar')
    expect(session).toHaveTextContent('Opus')
    expect(session).toHaveTextContent('socra')
    expect(screen.queryByRole('button', { name: /start agent/i })).toBeNull()
    expect(screen.getByTestId('state-label')).toHaveTextContent(/your turn/i)
    expect(screen.getByRole('button', { name: /agent and model/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /choose another folder/i })).toBeInTheDocument()
  })

  it('keeps listening-ready particles scattered until the session starts', () => {
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()

    expect(micOptions.protocolState).toBe('listening')
    expect(screen.getByTestId('orb-visualizer')).toHaveAttribute('data-protocol-state', 'idle')
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-resting', 'false')

    startSession(ws)
    expect(screen.getByTestId('orb-visualizer')).toHaveAttribute('data-protocol-state', 'listening')

    act(() => ws.receive({ type: 'state', state: 'speaking' }))
    expect(screen.getByTestId('orb-visualizer')).toHaveAttribute('data-protocol-state', 'speaking')
  })

  it('keeps a pending prompt visible beside the always-available context controls', () => {
    const { ws } = openPage()
    startSession(ws)
    act(() => ws.receive({ type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run git status', detail: '' }))

    expect(screen.getByRole('button', { name: 'Allow' })).toBeInTheDocument()
    expect(screen.getByTestId('session-bar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /agent and model/i })).toBeInTheDocument()
    expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'start_agent' }))
  })

  it('starts before the first recorded voice turn when context is ready', () => {
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()

    expect(micOptions.protocolState).toBe('listening')
    act(() => micOptions.onFinalize?.('UklGRg=='))

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' },
      { type: 'turn_audio', format: 'wav', data: 'UklGRg==' },
    ])
  })

  it('does not listen or submit voice before a required folder is chosen', () => {
    const { ws } = openPage()

    expect(micOptions.protocolState).toBe('idle')
    act(() => micOptions.onFinalize?.('UklGRg=='))

    expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'start_agent' }))
    expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'turn_audio' }))
  })

  it('continues listening during an accepted startup that is still idle', () => {
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()
    act(() => ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' }))

    expect(micOptions.protocolState).toBe('listening')
    act(() => micOptions.onFinalize?.('UklGRg=='))

    expect(ws.sent()).toContainEqual({ type: 'turn_audio', format: 'wav', data: 'UklGRg==' })
    expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'start_agent' }))
  })

  it('does not interrupt a pending session when the folder picker is cancelled', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()
    await user.type(screen.getByLabelText('Message the agent'), 'keep working{Enter}')
    act(() => ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' }))

    await user.click(screen.getByRole('button', { name: /choose another folder/i }))
    expect(ws.sent()).not.toContainEqual({ type: 'interrupt' })
    act(() => ws.receive({ type: 'agent_folder', path: null }))
    await user.type(screen.getByLabelText('Message the agent'), 'continue{Enter}')

    expect(ws.sent()).not.toContainEqual({ type: 'interrupt' })
    expect(ws.sent().filter((message) =>
      typeof message === 'object' && message !== null && 'type' in message && message.type === 'start_agent',
    )).toHaveLength(1)
    expect(ws.sent()).toContainEqual({ type: 'turn_text', text: 'continue' })
  })

  it('interrupts the old session only after a different folder is chosen', async () => {
    const user = userEvent.setup()
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()
    await user.type(screen.getByLabelText('Message the agent'), 'first turn{Enter}')
    act(() => ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' }))
    await user.click(screen.getByRole('button', { name: /choose another folder/i }))
    expect(ws.sent()).not.toContainEqual({ type: 'interrupt' })

    act(() => ws.receive({ type: 'agent_folder', path: 'D:\\code\\app' }))
    act(() => ws.receive({ ...backends, session: null }))
    await user.type(screen.getByLabelText('Message the agent'), 'new folder turn{Enter}')

    const folderRequest = ws.sent().findIndex((message) =>
      typeof message === 'object' && message !== null && 'type' in message && message.type === 'pick_folder',
    )
    expect(ws.sent().slice(folderRequest)).toEqual([
      { type: 'pick_folder' },
      { type: 'interrupt' },
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'D:\\code\\app' },
      { type: 'turn_text', text: 'new folder turn' },
    ])
  })

  it('uses the visualizer chosen in settings, shared with the exam page', async () => {
    window.localStorage.setItem(STORAGE_KEY_VISUALIZER, 'particle-lines')
    const user = userEvent.setup()
    openPage()

    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-style', 'lines')

    await user.click(screen.getByTestId('settings-button'))
    await user.click(screen.getByTestId('visualizer-particle-grid'))

    expect(window.localStorage.getItem(STORAGE_KEY_VISUALIZER)).toBe('particle-grid')
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-style', 'grid')
  })

  it('uses the particle shape chosen in settings, shared with the exam page', async () => {
    window.localStorage.setItem('socra_shape', 'wave')
    const user = userEvent.setup()
    openPage()
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'wave')

    await user.click(screen.getByTestId('settings-button'))
    await user.click(screen.getByTestId('shape-sphere'))

    expect(window.localStorage.getItem('socra_shape')).toBe('sphere')
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'sphere')
  })

  it('sends dictated and typed turns', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()
    startSession(ws)

    expect(micOptions.protocolState).toBe('listening')
    act(() => micOptions.onFinalize?.('UklGRg=='))
    await user.type(screen.getByLabelText('Message the agent'), 'list the files{Enter}')

    expect(ws.sent()).toContainEqual({ type: 'turn_audio', format: 'wav', data: 'UklGRg==' })
    expect(ws.sent()).toContainEqual({ type: 'turn_text', text: 'list the files' })
    expect(screen.getAllByRole('listitem').at(-1)).toHaveTextContent('list the files')
  })

  it('opens the code from a reply in its own pane and can close it', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()
    startSession(ws)

    expect(screen.queryByRole('region', { name: 'Code' })).toBeNull()
    act(() => ws.receive({ type: 'agent_reply', text: 'Added it:\n```ts\nconst retries = 3\n```' }))

    const pane = screen.getByRole('region', { name: 'Code' })
    expect(pane).toHaveTextContent('const retries = 3')
    expect(screen.getByRole('list', { name: 'Conversation' })).not.toHaveTextContent('const retries = 3')
    expect(screen.getByRole('list', { name: 'Conversation' })).toHaveTextContent('Added it:')

    await user.click(screen.getByRole('button', { name: 'Close code' }))
    expect(screen.queryByRole('region', { name: 'Code' })).toBeNull()

    act(() => ws.receive({ type: 'agent_reply', text: '```py\nprint(2)\n```' }))
    expect(screen.getByRole('region', { name: 'Code' })).toHaveTextContent('print(2)')
  })

  it('asks for permission on the page and sends the answer', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()
    startSession(ws)

    act(() => ws.receive({ type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run git status', detail: 'git status' }))
    await user.click(screen.getByRole('button', { name: 'Allow' }))

    expect(ws.sent()).toContainEqual({ type: 'permission_response', id: 'r1', allow: true })
    expect(screen.queryByRole('button', { name: 'Allow' })).toBeNull()
  })

  it('hides a prompt the server withdrew', () => {
    const { ws } = openPage()
    startSession(ws)

    act(() => ws.receive({ type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run', detail: '' }))
    act(() => ws.receive({ type: 'permission_closed', id: 'r1' }))

    expect(screen.queryByRole('button', { name: 'Deny' })).toBeNull()
  })

  it('lets the user stop the agent while it works', async () => {
    const user = userEvent.setup()
    const { ws } = openPage()
    startSession(ws)

    act(() => ws.receive({ type: 'state', state: 'thinking' }))
    await user.click(screen.getByRole('button', { name: 'Stop' }))

    expect(ws.sent()).toContainEqual({ type: 'interrupt' })
  })

  it('shows agent errors from the setup screen too', () => {
    const { ws } = openPage()

    act(() => ws.receive({ type: 'agent_error', message: 'Folder not found: C:\\gone' }))

    expect(screen.getByRole('alert')).toHaveTextContent('Folder not found: C:\\gone')
  })

  describe('project modes', () => {
    it('offers the three modes next to the folder and model once a session runs', () => {
      const { ws } = openPage()
      startSession(ws)

      expect(screen.getByRole('radiogroup', { name: /mode/i })).toBeInTheDocument()
      expect(screen.getByRole('radio', { name: 'Agent' })).toBeChecked()
      expect(screen.getByRole('radio', { name: 'Exam' })).toBeEnabled()
    })

    it('keeps the selector disabled until a session runs', () => {
      openPage()

      expect(screen.getByRole('radio', { name: 'Exam' })).toBeDisabled()
    })

    it('switches from the selector and continues the timeline with a condensed-context marker', async () => {
      const { ws } = openPage()
      startSession(ws)
      act(() => ws.receive({ type: 'agent_reply', text: 'Login added.' }))

      await userEvent.setup().click(screen.getByRole('radio', { name: 'Exam' }))
      expect(ws.sent().at(-1)).toEqual({ type: 'switch_mode', mode: 'exam' })
      act(() => ws.receive({ type: 'agent_switching', mode: 'exam' }))
      expect(screen.getByText('Switching to Exam…')).toBeVisible()
      act(() => ws.receive({
        type: 'agent_mode_changed', backend: 'claude-code', model: 'opus', cwd: 'C:\\work\\socra', mode: 'exam',
      }))

      expect(screen.getByRole('radio', { name: 'Exam' })).toBeChecked()
      const items = screen.getAllByRole('listitem')
      expect(items.map((item) => item.dataset.kind)).toEqual(['reply', 'handoff'])
      expect(items[0]).toHaveTextContent('Login added.')
      expect(items[1]).toHaveTextContent('Context condensed')
    })

    it('blocks mode switching on Pi and says why', () => {
      const { ws } = openPage()
      act(() => {
        ws.receive({ type: 'agent_started', backend: 'pi', model: 'anthropic/sonnet', cwd: 'C:\\work\\socra', mode: 'agent' })
        ws.receive({ type: 'state', state: 'listening' })
      })

      for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled()
      expect(screen.getByText('Mode switching needs Claude Code')).toBeVisible()
    })

    it('asks for confirmation of a voice-requested switch and answers it', async () => {
      const { ws } = openPage()
      startSession(ws)

      act(() => ws.receive({ type: 'mode_switch_request', mode: 'mentor', label: 'Mentor' }))
      expect(screen.getByRole('group', { name: 'Switch to Mentor mode?' })).toBeInTheDocument()
      expect(ws.sent().some((m) => (m as { type: string }).type === 'mode_switch_response')).toBe(false)
      await userEvent.setup().click(screen.getByRole('button', { name: 'Switch' }))

      expect(ws.sent().at(-1)).toEqual({ type: 'mode_switch_response', mode: 'mentor', allow: true })
      expect(screen.queryByRole('group', { name: /switch to/i })).toBeNull()
    })
  })
})
