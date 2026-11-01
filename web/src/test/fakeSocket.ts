import { vi } from 'vitest'

/** In-memory WebSocket for hook tests; install with `globalThis.WebSocket = FakeWebSocket`. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  static OPEN = 1
  static CLOSED = 3

  url: string
  readyState = 0
  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close'))
  })

  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  static latest(): FakeWebSocket {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1]
  }

  open() {
    this.readyState = FakeWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  receive(data: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(data) }))
  }

  drop(init?: CloseEventInit) {
    this.readyState = FakeWebSocket.CLOSED
    this.onclose?.(new CloseEvent('close', init))
  }

  sent(): unknown[] {
    return this.send.mock.calls.map(([raw]) => JSON.parse(raw as string))
  }
}

class FakeAudioSource {
  buffer: AudioBuffer | null = null
  connect = vi.fn()
  disconnect = vi.fn()
  start = vi.fn()
  stop = vi.fn()
  onended: (() => void) | null = null
}

class FakeConstantSource {
  offset = { value: 1 }
  connect = vi.fn()
  disconnect = vi.fn()
  start = vi.fn()
  stop = vi.fn()
}

/** Minimal AudioContext; finish clips with `FakeAudioContext.latest().sources[i].onended?.()`. */
export class FakeAudioContext {
  static instances: FakeAudioContext[] = []
  state = 'running'
  currentTime = 2
  destination = {}
  resume = vi.fn(async () => {})
  close = vi.fn(async () => {})
  decodeAudioData = vi.fn(async (_data: ArrayBuffer) => ({ duration: 0.25 }) as AudioBuffer)
  analyser = {
    fftSize: 256,
    connect: vi.fn(),
    disconnect: vi.fn(),
    getByteTimeDomainData: vi.fn((data: Uint8Array) => data.fill(128)),
  }
  sources: FakeAudioSource[] = []
  constantSources: FakeConstantSource[] = []
  createAnalyser = vi.fn(() => this.analyser)
  createConstantSource() {
    const source = new FakeConstantSource()
    this.constantSources.push(source)
    return source
  }
  createBufferSource() {
    const source = new FakeAudioSource()
    this.sources.push(source)
    return source
  }
  constructor() {
    FakeAudioContext.instances.push(this)
  }

  static latest(): FakeAudioContext {
    return FakeAudioContext.instances[FakeAudioContext.instances.length - 1]
  }
}
