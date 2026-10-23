import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'
import { STORAGE_KEY_MODE } from './lib/storage'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  readyState: number = MockWebSocket.OPEN
  send = vi.fn()
  close = vi.fn()

  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
    // Auto trigger open on next tick
    setTimeout(() => {
      this.onopen?.(new Event('open'))
    }, 0)
  }

  simulateMessage(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }
}

describe('App Integration', () => {
  const originalWebSocket = globalThis.WebSocket

  beforeEach(() => {
    window.localStorage.clear()
    MockWebSocket.instances = []
    globalThis.WebSocket = MockWebSocket as unknown as typeof WebSocket
  })

  afterEach(() => {
    globalThis.WebSocket = originalWebSocket
    vi.restoreAllMocks()
  })

  it('defaults to auto mode and persists mode changes in localStorage', async () => {
    const user = userEvent.setup()
    render(<App />)

    expect(document.querySelector('.shell > .background-pattern')).toHaveAttribute('aria-hidden', 'true')

    // Settings live behind the gear button
    await user.click(screen.getByTestId('settings-button'))

    // Initial state: auto is active
    const autoBtn = screen.getByTestId('mode-auto')
    const pttBtn = screen.getByTestId('mode-ptt')
    expect(autoBtn).toHaveAttribute('aria-checked', 'true')
    expect(pttBtn).toHaveAttribute('aria-checked', 'false')

    // Switch to push-to-talk
    await user.click(pttBtn)

    expect(pttBtn).toHaveAttribute('aria-checked', 'true')
    expect(autoBtn).toHaveAttribute('aria-checked', 'false')
    expect(window.localStorage.getItem(STORAGE_KEY_MODE)).toBe('push-to-talk')

    // Push to talk control should now be visible
    expect(screen.getByTestId('ptt-button')).toBeInTheDocument()
  })

  it('shows the title Socra and hides settings until the gear is opened', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Socra' })).toBeInTheDocument()
    expect(screen.queryByTestId('settings-panel')).not.toBeInTheDocument()
    await user.click(screen.getByTestId('settings-button'))
    expect(screen.getByTestId('settings-panel')).toBeInTheDocument()
    await user.keyboard('{Escape}')
    expect(screen.queryByTestId('settings-panel')).not.toBeInTheDocument()
  })

  it('updates the accessible connection indicator from WebSocket events', () => {
    render(<App />)
    const ws = MockWebSocket.instances[0]
    expect(screen.getByRole('status', { name: 'Connection: Connecting...' })).toBeVisible()

    act(() => ws.onopen?.(new Event('open')))
    expect(screen.getByRole('status', { name: 'Connection: Connected' })).toBeVisible()
    expect(screen.queryByRole('status', { name: 'Connection: Connecting...' })).not.toBeInTheDocument()

    act(() => ws.onclose?.(new CloseEvent('close')))
    expect(screen.getByRole('status', { name: 'Connection: Reconnecting…' })).toBeVisible()
    expect(screen.queryByRole('status', { name: 'Connection: Connected' })).not.toBeInTheDocument()
  })

  it('persists the chosen orb palette', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByTestId('settings-button'))
    await user.click(screen.getByTestId('palette-orchid'))
    expect(window.localStorage.getItem('socra_orb_palette')).toBe('orchid')
    expect(screen.getByTestId('palette-orchid')).toHaveAttribute('aria-checked', 'true')
  })

  it('switches the particles to the sound wave from settings and remembers it', async () => {
    const user = userEvent.setup()
    render(<App />)
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'sphere')
    await user.click(screen.getByTestId('settings-button'))
    await user.click(screen.getByTestId('shape-wave'))
    expect(window.localStorage.getItem('socra_shape')).toBe('wave')
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'wave')
  })

  it('updates state, question, and transcript from WebSocket messages', async () => {
    render(<App />)

    // Wait for ws instance
    expect(MockWebSocket.instances.length).toBeGreaterThan(0)
    const ws = MockWebSocket.instances[0]

    // Simulate incoming question
    act(() => {
      ws.simulateMessage({
        type: 'question',
        index: 3,
        total: 10,
        text: 'What is an atomic operation?',
      })
      ws.simulateMessage({
        type: 'state',
        state: 'speaking',
      })
    })

    expect(screen.getByTestId('question-index')).toHaveTextContent('Question 3/10')
    expect(screen.getByTestId('question-text')).toHaveTextContent('What is an atomic operation?')
    expect(screen.getByTestId('orb-visualizer')).toHaveAttribute('data-protocol-state', 'speaking')

    // Simulate transcript
    act(() => {
      ws.simulateMessage({
        type: 'transcript',
        text: '  Umm... a THREAD?\nNo, a process — I think.  ',
        final: true,
      })
    })

    expect(screen.getByTestId('transcript-text').textContent).toBe(
      '  Umm... a THREAD?\nNo, a process — I think.  '
    )
  })

  it('sends {"type":"reanswer"} when Re-answer button is clicked', async () => {
    const user = userEvent.setup()
    render(<App />)

    const ws = MockWebSocket.instances[0]

    const reanswerBtn = screen.getByTestId('reanswer-button')
    await user.click(reanswerBtn)

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'reanswer' }))
  })
  it('shows the finished screen over WebSocket and accepts the next exam question', () => {
    render(<App />)
    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.simulateMessage({ type: 'question', index: 1, total: 1, text: 'Read this code.', code: 'print(42)' })
    })
    expect(screen.getByRole('region', { name: 'Question code' })).toHaveTextContent('print(42)')
    act(() => {
      ws.simulateMessage({ type: 'state', state: 'idle' })
      ws.simulateMessage({ type: 'finished' })
    })
    expect(screen.getByText('Exam finished')).toBeInTheDocument()
    expect(screen.queryByTestId('question-panel')).not.toBeInTheDocument()
    expect(screen.queryByTestId('reanswer-button')).not.toBeInTheDocument()
    act(() => ws.simulateMessage({ type: 'question', index: 1, total: 2, text: 'New exam.' }))
    expect(screen.queryByText('Exam finished')).not.toBeInTheDocument()
    expect(screen.getByTestId('question-text')).toHaveTextContent('New exam.')
    expect(screen.queryByRole('region', { name: 'Question code' })).not.toBeInTheDocument()
  })

  it('switches to the light theme from settings and remembers it', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.click(screen.getByTestId('settings-button'))
    await user.click(screen.getByTestId('theme-light'))

    expect(document.documentElement.dataset.theme).toBe('light')
    expect(window.localStorage.getItem('socra_theme')).toBe('light')
  })

  it('sends a typed answer from the prompt line', async () => {
    const user = userEvent.setup()
    render(<App />)
    const ws = MockWebSocket.instances[0]
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    act(() => {
      ws.simulateMessage({ type: 'question', index: 1, total: 2, text: 'What is a mutex?' })
      ws.simulateMessage({ type: 'state', state: 'listening' })
    })

    await user.type(screen.getByLabelText('Type your answer'), 'A lock for one thread at a time{Enter}')

    expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'answer_text', text: 'A lock for one thread at a time' }))
    expect(screen.getByLabelText('Type your answer')).toHaveValue('')
  })

  it('shows question code in a code pane beside the question', () => {
    render(<App />)
    const ws = MockWebSocket.instances[0]
    act(() => ws.simulateMessage({ type: 'question', index: 1, total: 1, text: 'Read this code.', code: 'print(42)' }))

    expect(screen.getByRole('region', { name: 'Question code' })).toHaveTextContent('print(42)')
    expect(screen.getByTestId('question-panel')).not.toHaveTextContent('print(42)')
  })

  it('renders notice banner when notice message is received', () => {
    render(<App />)
    const ws = MockWebSocket.instances[0]
    expect(screen.queryByTestId('notice-banner')).not.toBeInTheDocument()

    act(() => {
      ws.simulateMessage({
        type: 'notice',
        text: "Didn't catch that. Please answer again.",
      })
    })

    const banner = screen.getByTestId('notice-banner')
    expect(banner).toBeInTheDocument()
    expect(banner).toHaveTextContent("Didn't catch that. Please answer again.")
  })

  describe('walkthrough', () => {
    const start = () => {
      render(<App />)
      const ws = MockWebSocket.instances[0]
      act(() => {
        ws.simulateMessage({ type: 'walkthrough', code: 'one\ntwo\nthree', language: 'python', total: 2 })
        ws.simulateMessage({ type: 'walkthrough_step', index: 1, total: 2, say: 'The middle one.', lines: [2, 2] })
      })
      return ws
    }

    it('shows the code with the step lines highlighted and what is being said', () => {
      start()
      const pane = screen.getByRole('region', { name: 'Walkthrough code' })
      const lines = Array.from(pane.querySelectorAll('code > span'))
      expect(lines.map((line) => line.hasAttribute('data-focused'))).toEqual([false, true, false])
      expect(screen.getByTestId('walkthrough-panel')).toHaveTextContent('The middle one.')
      expect(screen.queryByTestId('question-panel')).not.toBeInTheDocument()
    })

    it('sends the control buttons to the server', async () => {
      const user = userEvent.setup()
      const ws = start()
      await user.click(screen.getByRole('button', { name: 'Repeat' }))
      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'walkthrough_control', action: 'repeat' }))
    })

    it('lets the user type a command while it runs', async () => {
      const user = userEvent.setup()
      const ws = start()
      await user.type(screen.getByLabelText('Type your answer'), 'back{Enter}')
      expect(ws.send).toHaveBeenCalledWith(JSON.stringify({ type: 'answer_text', text: 'back' }))
    })

    it('goes back to the question view when the next question arrives', () => {
      const ws = start()
      act(() => ws.simulateMessage({ type: 'question', index: 1, total: 1, text: 'Why?' }))
      expect(screen.queryByTestId('walkthrough-panel')).not.toBeInTheDocument()
      expect(screen.getByTestId('question-panel')).toHaveTextContent('Why?')
    })
  })
})
