import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../src/index.css'
import AgentApp from '../src/AgentApp.tsx'
import App from '../src/App.tsx'

// 1. Shadow localStorage in-memory BEFORE components mount or read it
const memStore = new Map<string, string>()

// Pre-populate sensible defaults in memory
memStore.set('socra_mode', 'push-to-talk')
memStore.set('oral_exam_turn_mode', 'push-to-talk')
const currentTheme = document.documentElement.dataset.theme || 'dark'
memStore.set('socra_theme', currentTheme)

const mockStorage: Storage = {
  getItem: (key: string) => memStore.get(key) ?? null,
  setItem: (key: string, value: string) => {
    memStore.set(key, String(value))
  },
  removeItem: (key: string) => {
    memStore.delete(key)
  },
  clear: () => {
    memStore.clear()
  },
  key: (index: number) => Array.from(memStore.keys())[index] ?? null,
  get length() {
    return memStore.size
  },
}

Object.defineProperty(window, 'localStorage', {
  value: mockStorage,
  configurable: true,
  writable: false,
})

// 2. Mock navigator.mediaDevices.getUserMedia and enumerateDevices to prevent mic permission/hardware access
if (navigator.mediaDevices) {
  navigator.mediaDevices.getUserMedia = async () => {
    throw new DOMException('Simulated fixture: microphone disabled', 'NotAllowedError')
  }
  navigator.mediaDevices.enumerateDevices = async () => []
}

// 3. Mock public WebSocket protocol BEFORE rendering
const RealWebSocket = window.WebSocket

const searchParams = new URLSearchParams(window.location.search)
const isExam = searchParams.get('mode') === 'exam'
const splitQuery = searchParams.get('split') === '1' || searchParams.get('split') === 'true'
const initialStateQuery = searchParams.get('state') === 'speaking' ? 'speaking' : 'idle'

let activeWs: MockSocket | null = null

class MockSocket {
  static readonly OPEN = 1
  static readonly CLOSED = 3
  static readonly CONNECTING = 0
  static readonly CLOSING = 2

  readonly OPEN = 1
  readonly CLOSED = 3
  readonly CONNECTING = 0
  readonly CLOSING = 2

  readyState = MockSocket.CONNECTING
  onopen: ((ev: Event) => void) | null = null
  onclose: ((ev: CloseEvent) => void) | null = null
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: ((ev: Event) => void) | null = null

  private url: string
  private isAgentWs: boolean
  private isExamWs: boolean

  constructor(url: string | URL) {
    this.url = String(url)
    this.isAgentWs = this.url.includes('/ws/agent')
    this.isExamWs = this.url.includes('/ws') && !this.isAgentWs

    activeWs = this

    // Open asynchronously
    setTimeout(() => {
      if (this.readyState === MockSocket.CONNECTING) {
        this.readyState = MockSocket.OPEN
        this.onopen?.(new Event('open'))
        this.initDemoPayloads()
      }
    }, 10)
  }

  send(data: string) {
    try {
      const msg = JSON.parse(data)
      // Echo user typing in agent mode or exam mode
      if (msg.type === 'turn_text' && this.isAgentWs) {
        setTimeout(() => {
          this.receive({
            type: 'agent_reply',
            text: `Simulated response to: "${msg.text}". Lorem ipsum dolor sit amet, consectetur adipiscing elit. Integer nec odio. Praesent libero. Sed cursus ante dapibus diam.`,
          })
        }, 50)
      } else if (msg.type === 'answer_text' && this.isExamWs) {
        setTimeout(() => {
          this.receive({
            type: 'state',
            state: 'thinking',
          })
        }, 50)
      } else if (msg.type === 'interrupt' || msg.type === 'stop') {
        setTimeout(() => {
          this.receive({
            type: 'state',
            state: 'idle',
          })
        }, 10)
      }
    } catch {
      // ignore
    }
  }

  close() {
    this.readyState = MockSocket.CLOSED
    if (activeWs === this) {
      activeWs = null
    }
    this.onclose?.(new CloseEvent('close'))
  }

  receive(data: Record<string, unknown>) {
    if (this.readyState === MockSocket.OPEN && this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }))
    }
  }

  private initDemoPayloads() {
    if (this.isAgentWs) {
      // 1. backends with ready model
      this.receive({
        type: 'agent_backends',
        backends: [
          {
            id: 'claude-code',
            label: 'Claude Code',
            models: [{ id: 'sonnet', label: 'Sonnet 3.7' }],
            status: { state: 'ready' },
          },
        ],
        default: { backend: 'claude-code', model: 'sonnet' },
      })

      // 2. agent_started BEFORE replies (clears timeline)
      this.receive({
        type: 'agent_started',
        backend: 'claude-code',
        model: 'sonnet',
        cwd: '/demo/project',
      })

      // 3. state
      this.receive({
        type: 'state',
        state: initialStateQuery,
      })

      // 4. Populate ~40 long simulated replies so .shell-scroll genuinely overflows
      for (let i = 1; i <= 40; i++) {
        this.receive({
          type: 'agent_reply',
          text: `Reply #${i}: This is simulated conversation message ${i} designed to test viewport and timeline scrolling behavior. It contains multiple sentences describing operations, diagnostics, and code structure details so that desktop viewports genuinely overflow.`,
        })
      }

      // 5. Query split=1 includes fenced code
      if (splitQuery) {
        const sampleCode = Array.from({ length: 45 }, (_, idx) => `function demoOperation${idx}() {\n  console.log("running demo step ${idx}");\n  return ${idx} * 42;\n}`).join('\n\n')
        this.receive({
          type: 'agent_reply',
          text: `Here is the requested implementation with code blocks:\n\n\`\`\`typescript\n${sampleCode}\n\`\`\``,
        })
      }
    } else if (this.isExamWs) {
      const codeSnippet = splitQuery
        ? Array.from({ length: 40 }, (_, idx) => `const step${idx} = () => processMetric(${idx});`).join('\n')
        : undefined

      this.receive({
        type: 'question',
        index: 1,
        total: 5,
        text: 'This is a simulated exam question. ' + 'Exam question context and comprehensive problem breakdown. '.repeat(100),
        code: codeSnippet,
      })

      this.receive({
        type: 'state',
        state: initialStateQuery,
      })
    }
  }
}

// Preserve Vite HMR WebSocket: only intercept /ws and /ws/agent
window.WebSocket = function (url: string | URL, protocols?: string | string[]) {
  const urlStr = String(url)
  if (urlStr.includes('/ws/agent') || urlStr.includes('/ws')) {
    return new MockSocket(urlStr) as unknown as WebSocket
  }
  return new RealWebSocket(url, protocols)
} as unknown as typeof WebSocket
window.WebSocket.OPEN = RealWebSocket.OPEN
window.WebSocket.CLOSED = RealWebSocket.CLOSED
window.WebSocket.CONNECTING = RealWebSocket.CONNECTING
window.WebSocket.CLOSING = RealWebSocket.CLOSING

// Update document title and banner badge without reflowing production layout
document.title = `[SIMULATED FIXTURE] Socra - ${isExam ? 'Exam' : 'Agent'}`

const badge = document.createElement('div')
badge.setAttribute('data-testid', 'fixture-badge')
badge.textContent = 'SIMULATED DEMO FIXTURE (No backend / No audio)'
Object.assign(badge.style, {
  position: 'fixed',
  top: '2px',
  right: '80px',
  zIndex: '99999',
  fontSize: '10px',
  fontFamily: 'monospace',
  padding: '2px 6px',
  background: 'rgba(239, 68, 68, 0.85)',
  color: '#fff',
  borderRadius: '4px',
  pointerEvents: 'none',
})
document.body.appendChild(badge)

// Direct createRoot without src/main.tsx hydration
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {isExam ? <App /> : <AgentApp />}
  </StrictMode>,
)
