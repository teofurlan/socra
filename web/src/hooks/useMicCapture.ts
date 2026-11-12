import { useCallback, useEffect, useRef, useState } from 'react'
import type { ProtocolState, TurnMode } from '@/types/exam'
import { MicVAD } from '@ricky0123/vad-web'
import { AnswerSegmenter } from '@/lib/answerSegmenter'
import { encodeWAVBase64, hasSpeech } from '@/lib/wav'

const VAD_BASE_PATH = '/vad-assets/'
const PTT_MIN_HOLD_MS = 300
const VAD_SAMPLE_RATE = 16_000
// The legacy model's default 1400 ms redemption rounds down to 14 frames of 96 ms.
const VAD_REDEMPTION_MS = 1344
// Live transcript: the utterance so far is resent this often, capped to its latest seconds.
const PARTIAL_INTERVAL_MS = 1000
const PARTIAL_MAX_SECONDS = 30

export interface UseMicCaptureOptions {
  protocolState: ProtocolState
  mode: TurnMode
  silenceTimeoutMs: number
  /** Increments on each server listening message, including re-answer. */
  listeningEpoch?: number
  /** Selected microphone; '' or undefined uses the system default. */
  deviceId?: string
  onFinalize: (base64: string) => void
  /**
   * Receives a WAV of the whole utterance so far about every second while the user speaks,
   * until the answer is finalized. Without it nothing partial is captured or encoded.
   */
  onPartial?: (base64: string) => void
  /** The utterance ended without being sent, so whatever it showed provisionally is stale. */
  onPartialDiscard?: () => void
}

export interface UseMicCaptureResult {
  micError: string | null
  /** The selected microphone could not be opened, so the system default is in use. */
  micFallback: boolean
  getInputVolume: () => number
  silenceCountdownMs: number
  onTalkingChange: (talking: boolean) => void
}

interface AudioCapture {
  stream: MediaStream
  context: AudioContext
  analyser: AnalyserNode
  samples: Uint8Array<ArrayBuffer>
  sourceNode: MediaStreamAudioSourceNode
}

function buildAudioCapture(stream: MediaStream): AudioCapture {
  const context = new AudioContext()
  try {
    const analyser = context.createAnalyser()
    analyser.fftSize = 512
    const sourceNode = context.createMediaStreamSource(stream)
    sourceNode.connect(analyser)
    const samples = new Uint8Array(analyser.fftSize)
    return { stream, context, analyser, samples, sourceNode }
  } catch (error) {
    void context.close().catch(() => {})
    stream.getTracks().forEach((track) => track.stop())
    throw error
  }
}

async function teardownCapture(capture: AudioCapture | null): Promise<void> {
  if (!capture) return
  try { capture.sourceNode.disconnect() } catch { /* already disconnected */ }
  try { capture.analyser.disconnect() } catch { /* already disconnected */ }
  for (const track of capture.stream.getTracks()) track.stop()
  try { await capture.context.close() } catch { /* already closed */ }
}

function audioConstraints(deviceId?: string): MediaStreamConstraints {
  const processing = { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
  return { audio: deviceId ? { ...processing, deviceId: { exact: deviceId } } : processing }
}

/** The selected device is unplugged or no longer matches any input. */
function isMissingDevice(error: unknown): boolean {
  const name = (error as { name?: string } | null)?.name
  return name === 'OverconstrainedError' || name === 'NotFoundError'
}

interface OpenedStream {
  stream: MediaStream
  /** The selected deviceId that could not be opened, or null. */
  fallbackFor: string | null
}

/** Opens the selected microphone, or the system default when it is gone. */
async function openStream(selected: string): Promise<OpenedStream> {
  if (selected) {
    try {
      return { stream: await navigator.mediaDevices.getUserMedia(audioConstraints(selected)), fallbackFor: null }
    } catch (error) {
      if (!isMissingDevice(error)) throw error
      return { stream: await navigator.mediaDevices.getUserMedia(audioConstraints()), fallbackFor: selected }
    }
  }
  return { stream: await navigator.mediaDevices.getUserMedia(audioConstraints()), fallbackFor: null }
}

function micErrorMessage(error: unknown): string {
  if (error instanceof DOMException && error.name === 'NotAllowedError') {
    return 'Microphone access was denied. Please allow microphone access and try again.'
  }
  if (error instanceof DOMException && error.name === 'NotFoundError') {
    return 'No microphone found. Please connect a microphone and try again.'
  }
  return 'Could not access microphone. Check browser permissions.'
}

export function useMicCapture({
  protocolState, mode, silenceTimeoutMs, listeningEpoch = 0, deviceId = '', onFinalize, onPartial, onPartialDiscard,
}: UseMicCaptureOptions): UseMicCaptureResult {
  const [micError, setMicError] = useState<string | null>(null)
  const [fallbackFor, setFallbackFor] = useState<string | null>(null)
  // Derived, so a new selection hides a note that belonged to the previous one.
  const micFallback = fallbackFor !== null && fallbackFor === deviceId
  const [silenceCountdownMs, setSilenceCountdownMs] = useState(0)
  const captureRef = useRef<AudioCapture | null>(null)
  const vadRef = useRef<MicVAD | null>(null)
  const segmenterRef = useRef(new AnswerSegmenter())
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const countdownRafRef = useRef<number | null>(null)
  const generationRef = useRef(0)
  const sentRef = useRef(false)
  const listeningEpochRef = useRef(listeningEpoch)
  const pttRequestRef = useRef(0)
  const pttPressedRef = useRef(false)
  const pttPressTimeRef = useRef(0)
  const pttChunksRef = useRef<Float32Array[]>([])
  const pttProcessorRef = useRef<ScriptProcessorNode | null>(null)
  const partialTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const speechFramesRef = useRef<Float32Array[]>([])
  const speechActiveRef = useRef(false)
  const onPartialRef = useRef(onPartial)
  useEffect(() => { onPartialRef.current = onPartial }, [onPartial])
  const onPartialDiscardRef = useRef(onPartialDiscard)
  useEffect(() => { onPartialDiscardRef.current = onPartialDiscard }, [onPartialDiscard])
  const onFinalizeRef = useRef(onFinalize)
  useEffect(() => { onFinalizeRef.current = onFinalize }, [onFinalize])
  const silenceTimeoutRef = useRef(silenceTimeoutMs)
  useEffect(() => { silenceTimeoutRef.current = silenceTimeoutMs }, [silenceTimeoutMs])
  const deviceIdRef = useRef(deviceId)
  useEffect(() => { deviceIdRef.current = deviceId }, [deviceId])

  const getInputVolume = useCallback(() => {
    const capture = captureRef.current
    if (!capture || capture.context.state !== 'running') return 0
    capture.analyser.getByteTimeDomainData(capture.samples)
    let sum = 0
    for (const s of capture.samples) sum += (s / 128 - 1) ** 2
    return Math.min(1, Math.sqrt(sum / capture.samples.length) * 3)
  }, [])

  const clearSilenceTimer = useCallback(() => {
    if (silenceTimerRef.current !== null) clearTimeout(silenceTimerRef.current)
    silenceTimerRef.current = null
    if (countdownRafRef.current !== null) cancelAnimationFrame(countdownRafRef.current)
    countdownRafRef.current = null
    setSilenceCountdownMs(0)
  }, [])

  const stopPartials = useCallback(() => {
    if (partialTimerRef.current !== null) clearInterval(partialTimerRef.current)
    partialTimerRef.current = null
    speechFramesRef.current = []
    speechActiveRef.current = false
  }, [])

  /** Resends the utterance so far each interval, only when it grew; never after stopCapture. */
  const startPartials = useCallback((
    collect: () => { chunks: Float32Array[]; sampleRate: number },
    isCurrent: () => boolean,
  ) => {
    if (partialTimerRef.current !== null || !onPartialRef.current) return
    let sentLength = 0
    partialTimerRef.current = setInterval(() => {
      const emit = onPartialRef.current
      if (!emit || !isCurrent()) return
      const { chunks, sampleRate } = collect()
      const merged = AnswerSegmenter.merge(chunks)
      if (merged.length <= sentLength) return
      sentLength = merged.length
      const tail = merged.length > sampleRate * PARTIAL_MAX_SECONDS
        ? merged.slice(merged.length - sampleRate * PARTIAL_MAX_SECONDS)
        : merged
      const base64 = encodeWAVBase64(tail, sampleRate)
      if (base64) emit(base64)
    }, PARTIAL_INTERVAL_MS)
  }, [])

  const stopCapture = useCallback(() => {
    clearSilenceTimer()
    stopPartials()
    pttPressedRef.current = false
    ++pttRequestRef.current
    const proc = pttProcessorRef.current
    pttProcessorRef.current = null
    if (proc) {
      proc.onaudioprocess = null
      try { proc.disconnect() } catch { /* already disconnected */ }
    }
    pttChunksRef.current = []
    // Detach synchronously: a slow destroy must not take the next turn's resources.
    const capture = captureRef.current
    captureRef.current = null
    const vad = vadRef.current
    vadRef.current = null
    void teardownCapture(capture)
    if (vad) void vad.destroy().catch(() => {})
    segmenterRef.current.send({ kind: 'reset' })
  }, [clearSilenceTimer, stopPartials])

  const doFinalize = useCallback((segments: Float32Array[]) => {
    clearSilenceTimer()
    if (sentRef.current) return
    const merged = AnswerSegmenter.merge(segments)
    if (!hasSpeech(merged)) {
      segmenterRef.current.send({ kind: 'reset' })
      onPartialDiscardRef.current?.()
      return
    }
    const base64 = encodeWAVBase64(merged, VAD_SAMPLE_RATE)
    if (base64) {
      sentRef.current = true
      stopCapture()
      onFinalizeRef.current(base64)
    }
  }, [clearSilenceTimer, stopCapture])

  const handleSegmenterAction = useCallback((action: ReturnType<AnswerSegmenter['send']>) => {
    if (!action) return
    if (action.type === 'startTimer') {
      clearSilenceTimer()
      // VAD has already waited through redemption since the last speech frame.
      const ms = Math.max(0, silenceTimeoutRef.current - VAD_REDEMPTION_MS)
      const deadline = Date.now() + ms
      const tick = () => {
        const remaining = Math.max(0, deadline - Date.now())
        setSilenceCountdownMs(remaining)
        countdownRafRef.current = remaining > 0 ? requestAnimationFrame(tick) : null
      }
      setSilenceCountdownMs(ms)
      countdownRafRef.current = requestAnimationFrame(tick)
      silenceTimerRef.current = setTimeout(() => {
        silenceTimerRef.current = null
        handleSegmenterAction(segmenterRef.current.send({ kind: 'silenceExpired' }))
      }, ms)
    } else if (action.type === 'cancelTimer') {
      clearSilenceTimer()
    } else {
      doFinalize(action.segments)
    }
  }, [clearSilenceTimer, doFinalize])

  const startAutoVAD = useCallback(async (generation: number) => {
    const isCurrent = () => generation === generationRef.current && !sentRef.current
    setMicError(null)
    let opened: OpenedStream
    try {
      opened = await openStream(deviceIdRef.current)
    } catch (error) {
      if (isCurrent()) setMicError(micErrorMessage(error))
      return
    }
    const { stream } = opened
    if (!isCurrent()) {
      stream.getTracks().forEach((track) => track.stop())
      return
    }
    setFallbackFor(opened.fallbackFor)
    let capture: AudioCapture | null = null
    try {
      capture = buildAudioCapture(stream)
      captureRef.current = capture
      segmenterRef.current = new AnswerSegmenter()
      const vad = await MicVAD.new({
        getStream: async () => stream,
        // Own this context even if VAD initialization finishes after cleanup.
        audioContext: capture.context,
        baseAssetPath: VAD_BASE_PATH,
        onnxWASMBasePath: VAD_BASE_PATH,
        startOnLoad: true,
        redemptionMs: VAD_REDEMPTION_MS,
        onSpeechStart: () => {
          if (!isCurrent()) return
          speechActiveRef.current = true
          speechFramesRef.current = []
          startPartials(
            () => ({
              chunks: [...segmenterRef.current.segments, ...speechFramesRef.current],
              sampleRate: VAD_SAMPLE_RATE,
            }),
            isCurrent,
          )
          handleSegmenterAction(segmenterRef.current.send({ kind: 'speechStart' }))
        },
        // The segment only arrives when speech ends, so the frames in between feed the partials.
        onFrameProcessed: (_probabilities: unknown, frame: Float32Array) => {
          if (speechActiveRef.current && onPartialRef.current) speechFramesRef.current.push(new Float32Array(frame))
        },
        onSpeechEnd: (audio: Float32Array) => {
          if (!isCurrent()) return
          speechActiveRef.current = false
          handleSegmenterAction(segmenterRef.current.send({ kind: 'speechEnd', audio }))
          speechFramesRef.current = []
        },
        onVADMisfire: () => {
          speechActiveRef.current = false
          speechFramesRef.current = []
          if (isCurrent()) handleSegmenterAction(segmenterRef.current.send({ kind: 'speechMisfire' }))
        },
      })
      if (!isCurrent()) {
        await vad.destroy()
        return
      }
      vadRef.current = vad
    } catch (error) {
      console.error('VAD init failed:', error)
      // Dispose only this initialization's resources, not a replacement turn.
      if (captureRef.current === capture) {
        captureRef.current = null
        await teardownCapture(capture)
      } else if (!capture) {
        stream.getTracks().forEach((track) => track.stop())
      }
      if (isCurrent()) setMicError('Voice activity detection could not start. Check console for details.')
    }
  }, [handleSegmenterAction, startPartials])

  const finalizePTT = useCallback(() => {
    const chunks = pttChunksRef.current
    const capture = captureRef.current
    const holdMs = Date.now() - pttPressTimeRef.current
    const sampleRate = capture?.context.sampleRate ?? 44100
    stopCapture() // Also release short and empty captures.
    if (holdMs < PTT_MIN_HOLD_MS || sentRef.current) {
      if (!sentRef.current) onPartialDiscardRef.current?.()
      return
    }
    const merged = AnswerSegmenter.merge(chunks)
    if (!hasSpeech(merged)) {
      onPartialDiscardRef.current?.()
      return
    }
    const base64 = encodeWAVBase64(merged, sampleRate)
    if (base64) {
      sentRef.current = true
      onFinalizeRef.current(base64)
    }
  }, [stopCapture])

  const onTalkingChange = useCallback((talking: boolean) => {
    if (protocolState !== 'listening' || mode !== 'push-to-talk' || sentRef.current) return
    if (pttPressedRef.current === talking) return
    pttPressedRef.current = talking
    if (!talking) {
      finalizePTT()
      return
    }
    const request = ++pttRequestRef.current
    const generation = generationRef.current
    const isCurrent = () => request === pttRequestRef.current && generation === generationRef.current && pttPressedRef.current && !sentRef.current
    pttPressTimeRef.current = Date.now()
    pttChunksRef.current = []
    setMicError(null)
    // The promise boundary also catches an unavailable mediaDevices API.
    void Promise.resolve().then(() => openStream(deviceIdRef.current)).then(({ stream, fallbackFor: failed }) => {
      if (!isCurrent()) {
        stream.getTracks().forEach((track) => track.stop())
        return
      }
      setFallbackFor(failed)
      try {
        captureRef.current = buildAudioCapture(stream)
        const { context, sourceNode } = captureRef.current
        const proc = context.createScriptProcessor(4096, 1, 1)
        pttProcessorRef.current = proc
        proc.onaudioprocess = (event) => {
          if (isCurrent()) pttChunksRef.current.push(new Float32Array(event.inputBuffer.getChannelData(0)))
        }
        sourceNode.connect(proc)
        proc.connect(context.destination)
        startPartials(() => ({ chunks: pttChunksRef.current, sampleRate: context.sampleRate }), isCurrent)
      } catch (error) {
        stream.getTracks().forEach((track) => track.stop())
        throw error
      }
    }).catch((error) => {
      if (!isCurrent()) return
      stopCapture()
      onPartialDiscardRef.current?.()
      setMicError(micErrorMessage(error))
    })
  }, [finalizePTT, mode, protocolState, startPartials, stopCapture])

  // A new deviceId restarts listening on that microphone; unsent audio of the turn is dropped.
  useEffect(() => {
    const generation = ++generationRef.current
    if (listeningEpochRef.current !== listeningEpoch) {
      listeningEpochRef.current = listeningEpoch
      sentRef.current = false
    }
    if (protocolState !== 'listening') {
      sentRef.current = false
      stopCapture()
      return
    }
    if (mode === 'auto' && !sentRef.current) void startAutoVAD(generation)
    return () => {
      ++generationRef.current
      // Capture cancelled (new device, mode or state): an unsent utterance leaves no stale text.
      if (!sentRef.current) onPartialDiscardRef.current?.()
      stopCapture()
    }
  }, [protocolState, mode, listeningEpoch, deviceId, startAutoVAD, stopCapture])

  return { micError, micFallback, getInputVolume, silenceCountdownMs, onTalkingChange }
}
