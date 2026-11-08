import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AgentApp from './AgentApp'
import { FakeAudioContext, FakeWebSocket } from '@/test/fakeSocket'
import { STORAGE_KEY_AGENT_FOLDER, STORAGE_KEY_AGENT_SELECTION } from '@/lib/storage'

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

  describe('scenes', () => {
    const playScene = (ws: FakeWebSocket) => {
      startSession(ws)
      act(() => {
        ws.receive({
          type: 'walkthrough',
          title: 'Adding',
          objects: [{ id: 'src', primitive: 'code', params: { code: 'one\ntwo\nthree', language: 'python' }, hidden: false }],
          total: 2,
        })
        ws.receive({ type: 'walkthrough_step', index: 1, total: 2, id: 'mid', say: 'The middle one.', state: { src: { visible: true, lines: [2, 2] } } })
      })
    }

    it('shows what is being said and the scene code with its focus', () => {
      const { ws } = openPage()
      playScene(ws)
      expect(screen.getByTestId('walkthrough-panel')).toHaveTextContent('The middle one.')
      const pane = screen.getByRole('region', { name: 'Walkthrough code' })
      const lines = Array.from(pane.querySelectorAll('code > span'))
      expect(lines.map((line) => line.hasAttribute('data-focused'))).toEqual([false, true, false])
    })

    it('points the particles at the focused lines while the scene plays, and lets go once it ends', () => {
      const { ws } = openPage()
      playScene(ws)
      const visualizer = screen.getByTestId('particle-visualizer')
      expect(visualizer).toHaveAttribute('data-figures', 'focus:src:2-2')
      expect(document.querySelector('pre[data-scene-object="src"]')).toBeInTheDocument()
      act(() => ws.receive({ type: 'walkthrough_status', status: 'ended', reason: 'completed' }))
      // The last step stays up after a completed scene, even when the user speaks, until the agent clears it.
      expect(visualizer).toHaveAttribute('data-figures', 'focus:src:2-2')
      expect(document.querySelector('pre[data-scene-object="src"]')).toBeInTheDocument()
      act(() => ws.receive({ type: 'transcript', text: 'why?', final: true }))
      expect(visualizer).toHaveAttribute('data-figures', 'focus:src:2-2')
      act(() => ws.receive({ type: 'walkthrough_cleared' }))
      expect(visualizer).toHaveAttribute('data-figures', '')
    })

    it('clears the figures at once when the scene was stopped', () => {
      const { ws } = openPage()
      playScene(ws)
      act(() => ws.receive({ type: 'walkthrough_status', status: 'ended', reason: 'stopped' }))
      expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-figures', '')
    })

    it('forms the headline with the particles and keeps its text for screen readers', () => {
      const { ws } = openPage()
      startSession(ws)
      act(() => {
        ws.receive({ type: 'walkthrough', title: 'T', objects: [{ id: 'h', primitive: 'headline', params: { text: 'Big idea' }, hidden: false }], total: 1 })
        ws.receive({ type: 'walkthrough_step', index: 1, total: 1, id: 's1', say: 'Hi.', state: { h: { visible: true, text: 'Big idea' } } })
      })
      expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-figures', 'headline:h:Big idea')
      const text = screen.getByTestId('scene-headline')
      expect(text).toHaveTextContent('Big idea')
      expect(text).toHaveAttribute('aria-live', 'polite')
      act(() => ws.receive({ type: 'walkthrough_status', status: 'ended', reason: 'completed' }))
      expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-figures', 'headline:h:Big idea')
      expect(screen.getByTestId('scene-headline')).toHaveTextContent('Big idea')
      act(() => ws.receive({ type: 'transcript', text: 'ok', final: true }))
      expect(screen.getByTestId('scene-headline')).toHaveTextContent('Big idea')
      act(() => ws.receive({ type: 'walkthrough_cleared' }))
      expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-figures', '')
      expect(screen.queryByTestId('scene-headline')).not.toBeInTheDocument()
    })

    describe('pointing at the finished scene', () => {
      const objects = [
        { id: 'src', primitive: 'code', params: { code: 'one\ntwo\nthree', language: 'python' }, hidden: false },
        {
          id: 'flow', primitive: 'diagram', hidden: false,
          params: { nodes: [{ id: 'api', label: 'API' }, { id: 'db', label: 'DB' }], edges: [{ from: 'api', to: 'db' }] },
        },
        {
          id: 'arr', primitive: 'structure', hidden: false,
          params: { kind: 'array', items: [4, 5, 6], initial: { kind: 'array', items: [4, 5, 6], last: null } },
        },
      ]
      const state = {
        src: { visible: true, lines: null },
        flow: { visible: true, highlighted: [], dimmed: [], revealed: [{ from: 'api', to: 'db' }], trace: [], notes: {} },
        arr: { visible: true, kind: 'array', items: [4, 5, 6], last: null },
      }
      const finished = () => {
        const { ws } = openPage()
        startSession(ws)
        act(() => {
          ws.receive({ type: 'walkthrough', title: 'All', objects, total: 1 })
          ws.receive({ type: 'walkthrough_step', index: 1, total: 1, id: 's1', say: 'Everything.', state })
          ws.receive({ type: 'walkthrough_status', status: 'ended', reason: 'completed' })
        })
        return ws
      }
      const figures = () => screen.getByTestId('particle-visualizer').getAttribute('data-figures')

      it('highlights a pointed diagram node and the particles ring it', () => {
        const ws = finished()
        expect(figures()).toBe('')
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'flow', part: 'db' }] }))
        expect(document.querySelector('[data-diagram-node="db"]')).toHaveAttribute('data-highlighted', 'true')
        expect(document.querySelector('[data-diagram-node="api"]')).not.toHaveAttribute('data-highlighted')
        expect(figures()).toBe('highlight:flow:db')
      })

      it('marks a pointed structure part and the particles outline it', () => {
        const ws = finished()
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'arr', part: 'cell:1' }] }))
        expect(document.querySelector('[data-structure-part="cell:1"]')).toHaveAttribute('data-touched', 'true')
        expect(document.querySelector('[data-structure-part="cell:0"]')).not.toHaveAttribute('data-touched')
        expect(figures()).toBe('point:arr:cell:1')
      })

      it('focuses a pointed line range and the particles outline it', () => {
        const ws = finished()
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'src', lines: [2, 3] }] }))
        const pane = screen.getByRole('region', { name: 'Walkthrough code src' })
        expect(Array.from(pane.querySelectorAll('code > span')).map((line) => line.hasAttribute('data-focused'))).toEqual([false, true, true])
        expect(figures()).toBe('focus:src:2-3')
      })

      it('emphasizes a whole object for a bare target, and an empty list takes it away', () => {
        const ws = finished()
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'flow' }] }))
        expect(document.querySelectorAll('[data-diagram-node][data-highlighted="true"]')).toHaveLength(2)
        act(() => ws.receive({ type: 'walkthrough_point', targets: [] }))
        expect(document.querySelectorAll('[data-diagram-node][data-highlighted="true"]')).toHaveLength(0)
        expect(figures()).toBe('')
      })

      it('animates a prediction result on that structure and removes the pointing', () => {
        const ws = finished()
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'arr', part: 'cell:0' }] }))
        act(() => ws.receive({
          type: 'walkthrough_result', object: 'arr',
          state: { visible: true, kind: 'array', items: [4, 9, 6], last: { op: 'set', index: 1, value: 9, previous: 5 } },
        }))
        expect(document.querySelector('[data-structure-part="cell:1"]')).toHaveTextContent('9')
        expect(document.querySelector('[data-structure-part="cell:1"]')).toHaveAttribute('data-touched', 'true')
        expect(figures()).toMatch(/^touch:arr:/) // animated like a step; the pointing is gone
        expect(screen.getByRole('region', { name: 'Walkthrough code src' })).toBeInTheDocument()
      })

      it('shows a replayed step after the scene ended and stays on it', () => {
        const ws = finished()
        act(() => ws.receive({
          type: 'walkthrough_step', index: 1, total: 1, id: 's1', say: 'Everything.',
          state: { ...state, src: { visible: true, lines: [2, 3] } },
        }))
        act(() => ws.receive({ type: 'walkthrough_status', status: 'ended', reason: 'completed' }))
        const pane = screen.getByRole('region', { name: 'Walkthrough code src' })
        expect(Array.from(pane.querySelectorAll('code > span')).map((line) => line.hasAttribute('data-focused'))).toEqual([false, true, true])
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'flow' }] }))
        expect(document.querySelectorAll('[data-diagram-node][data-highlighted="true"]')).toHaveLength(2)
      })

      it('lets go of the pointing with the scene', () => {
        const ws = finished()
        act(() => ws.receive({ type: 'walkthrough_point', targets: [{ object: 'src', lines: [1, 1] }] }))
        act(() => ws.receive({ type: 'walkthrough_cleared' }))
        expect(figures()).toBe('')
      })
    })

    it('points the particles at nothing without a scene', () => {
      const { ws } = openPage()
      startSession(ws)
      expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-figures', '')
    })

    it('sends the controls to the server', async () => {
      const user = userEvent.setup()
      const { ws } = openPage()
      playScene(ws)
      await user.click(screen.getByRole('button', { name: 'Stop' }))
      expect(ws.sent()).toContainEqual({ type: 'walkthrough_control', action: 'stop' })
    })
  })

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

    await user.type(screen.getByLabelText('Message Socra'), 'list the files{Enter}')

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' },
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

    await user.type(screen.getByLabelText('Message Socra'), 'keep this prompt{Enter}')

    expect(screen.getByLabelText('Message Socra')).toHaveValue('keep this prompt')
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

    await user.type(screen.getByLabelText('Message Socra'), 'inspect the project{Enter}')

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' },
      { type: 'turn_text', text: 'inspect the project' },
    ])
    expect(screen.getByLabelText('Message Socra')).toHaveValue('')
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

  it('keeps pending decisions outside the scrolling conversation', () => {
    const { ws } = openPage()
    startSession(ws)
    act(() => {
      ws.receive({ type: 'permission_request', id: 'r1', tool: 'Bash', title: 'Run git status', detail: '' })
      ws.receive({ type: 'mode_switch_request', mode: 'mentor', label: 'Mentor' })
    })

    const permission = screen.getByRole('button', { name: 'Allow' })
    const modeSwitch = screen.getByRole('group', { name: 'Switch to Mentor mode?' })
    for (const card of [permission, modeSwitch]) {
      expect(card.closest('.decision-dock')).not.toBeNull()
      expect(card.closest('.shell-scroll')).toBeNull()
    }
  })

  it('starts before the first recorded voice turn when context is ready', () => {
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
    const { ws } = openPage()

    expect(micOptions.protocolState).toBe('listening')
    act(() => micOptions.onFinalize?.('UklGRg=='))

    expect(ws.sent().slice(-2)).toEqual([
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' },
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
    await user.type(screen.getByLabelText('Message Socra'), 'keep working{Enter}')
    act(() => ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' }))

    await user.click(screen.getByRole('button', { name: /choose another folder/i }))
    expect(ws.sent()).not.toContainEqual({ type: 'interrupt' })
    act(() => ws.receive({ type: 'agent_folder', path: null }))
    await user.type(screen.getByLabelText('Message Socra'), 'continue{Enter}')

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
    await user.type(screen.getByLabelText('Message Socra'), 'first turn{Enter}')
    act(() => ws.receive({ type: 'agent_started', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' }))
    await user.click(screen.getByRole('button', { name: /choose another folder/i }))
    expect(ws.sent()).not.toContainEqual({ type: 'interrupt' })

    act(() => ws.receive({ type: 'agent_folder', path: 'D:\\code\\app' }))
    act(() => ws.receive({ ...backends, session: null }))
    await user.type(screen.getByLabelText('Message Socra'), 'new folder turn{Enter}')

    const folderRequest = ws.sent().findIndex((message) =>
      typeof message === 'object' && message !== null && 'type' in message && message.type === 'pick_folder',
    )
    expect(ws.sent().slice(folderRequest)).toEqual([
      { type: 'pick_folder' },
      { type: 'interrupt' },
      { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'D:\\code\\app', mode: 'mentor' },
      { type: 'turn_text', text: 'new folder turn' },
    ])
  })

  it.each(['particle-lines', 'particle-letters', 'particle-grid'])('loads with the retired look %s still stored, offering no look in settings', async (look) => {
    window.localStorage.setItem('socra_visualizer', look)
    const user = userEvent.setup()
    openPage()

    expect(screen.getByTestId('particle-visualizer')).toBeInTheDocument()
    await user.click(screen.getByTestId('settings-button'))
    expect(screen.queryByRole('radiogroup', { name: 'Visualizer' })).toBeNull()
    expect(screen.getByRole('radiogroup', { name: 'Shape' })).toBeInTheDocument()
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
    await user.type(screen.getByLabelText('Message Socra'), 'list the files{Enter}')

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
    it('offers the two modes next to the folder and model once a session runs', () => {
      const { ws } = openPage()
      startSession(ws)

      expect(screen.getByRole('radiogroup', { name: /mode/i })).toBeInTheDocument()
      expect(screen.getAllByRole('radio').map((radio) => radio.textContent)).toEqual(['Mentor', 'Exam'])
      expect(screen.getByRole('radio', { name: 'Mentor' })).toBeChecked()
      expect(screen.getByRole('radio', { name: 'Exam' })).toBeEnabled()
    })

    it('starts a new session in mentor by default', async () => {
      const user = userEvent.setup()
      window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
      const { ws } = openPage()

      expect(screen.getByRole('radio', { name: 'Mentor' })).toBeChecked()
      await user.type(screen.getByLabelText('Message Socra'), 'hello{Enter}')

      expect(ws.sent()).toContainEqual(
        { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' },
      )
    })

    it('falls back to mentor when a resynced session reports no mode', () => {
      const { ws } = openPage()
      act(() => ws.receive({
        ...backends,
        session: { backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra' },
      }))

      expect(screen.getByRole('radio', { name: 'Mentor' })).toBeChecked()
      expect(screen.getByRole('radio', { name: 'Exam' })).not.toBeChecked()
    })

    it('picks the starting mode before a session runs and starts in it', async () => {
      const user = userEvent.setup()
      window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, 'C:\\work\\socra')
      const { ws } = openPage()

      await user.click(screen.getByRole('radio', { name: 'Mentor' }))
      expect(screen.getByRole('radio', { name: 'Mentor' })).toBeChecked()
      expect(ws.sent()).not.toContainEqual(expect.objectContaining({ type: 'switch_mode' }))

      await user.type(screen.getByLabelText('Message Socra'), 'explain the server{Enter}')
      expect(ws.sent()).toContainEqual(
        { type: 'start_agent', backend: 'claude-code', model: 'sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' },
      )
    })

    it('keeps the selector disabled before a session when the chosen agent has no modes', () => {
      window.localStorage.setItem(STORAGE_KEY_AGENT_SELECTION, JSON.stringify({ backend: 'pi', model: 'anthropic/sonnet' }))
      openPage()

      expect(screen.getByRole('radio', { name: 'Exam' })).toBeDisabled()
      expect(screen.getByText('Mode switching needs Claude Code')).toBeVisible()
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
        ws.receive({ type: 'agent_started', backend: 'pi', model: 'anthropic/sonnet', cwd: 'C:\\work\\socra', mode: 'mentor' })
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
