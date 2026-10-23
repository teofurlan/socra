import { useCallback, useEffect, useRef } from 'react'

interface Playback {
  context: AudioContext
  analyser: AnalyserNode
  samples: Uint8Array<ArrayBuffer>
  sources: Set<AudioBufferSourceNode>
  queue: Promise<void>
  nextStart: number
  /** Bumped by stopAudio so clips still decoding are dropped. */
  generation: number
  disposed: boolean
}

export function useExamAudio() {
  const playbackRef = useRef<Playback | null>(null)

  /** ``onStart`` runs when this clip's sound begins, not when it is queued. */
  const playAudio = useCallback((base64: string, onDone?: () => void, onStart?: () => void) => {
    let doneCalled = false
    const notifyDone = () => {
      if (!doneCalled) {
        doneCalled = true
        onDone?.()
      }
    }
    if (!playbackRef.current) {
      try {
        const context = new AudioContext()
        const analyser = context.createAnalyser()
        analyser.fftSize = 256
        analyser.connect(context.destination)
        playbackRef.current = {
          context, analyser, samples: new Uint8Array(analyser.fftSize),
          sources: new Set(), queue: Promise.resolve(), nextStart: 0, generation: 0, disposed: false,
        }
      } catch (err) {
        console.error('Failed to create AudioContext:', err)
        notifyDone()
        return
      }
    }
    const playback = playbackRef.current
    const { context, analyser } = playback
    const generation = playback.generation
    // A browser may require a user gesture before sound can begin.
    if (context.state === 'suspended') {
      void context.resume().catch((error) => console.warn('Audio needs a user gesture:', error))
    }
    playback.queue = playback.queue.then(async () => {
      if (playback.disposed || playback.generation !== generation) {
        notifyDone()
        return
      }
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0))
      const buffer = await context.decodeAudioData(bytes.buffer)
      if (playback.disposed || playback.generation !== generation) {
        notifyDone()
        return
      }
      const source = context.createBufferSource()
      source.buffer = buffer
      source.connect(analyser)
      playback.sources.add(source)
      source.onended = () => {
        source.disconnect()
        playback.sources.delete(source)
        notifyDone()
      }
      const start = Math.max(context.currentTime, playback.nextStart)
      source.start(start)
      playback.nextStart = start + buffer.duration
      if (onStart) {
        const delayMs = (start - context.currentTime) * 1000
        if (delayMs > 20) {
          setTimeout(() => {
            if (!playback.disposed && playback.generation === generation) onStart()
          }, delayMs)
        } else {
          onStart()
        }
      }
    }).catch((error) => {
      if (!playback.disposed) console.error('Failed to play exam audio:', error)
      notifyDone()
    })
  }, [])

  /** Silence everything now; each stopped or pending clip still reports done once. */
  const stopAudio = useCallback(() => {
    const playback = playbackRef.current
    if (!playback || playback.disposed) return
    playback.generation += 1
    for (const source of [...playback.sources]) {
      const ended = source.onended
      source.onended = null
      try {
        source.stop()
      } catch (error) {
        console.warn('Could not stop audio clip:', error)
      }
      // Runs the clip's own cleanup and its onDone callback.
      ended?.call(source, new Event('ended'))
    }
    playback.nextStart = 0
  }, [])

  const getOutputVolume = useCallback(() => {
    const playback = playbackRef.current
    if (!playback || playback.disposed || playback.context.state !== 'running') return 0
    playback.analyser.getByteTimeDomainData(playback.samples)
    let sum = 0
    for (const sample of playback.samples) sum += (sample / 128 - 1) ** 2
    return Math.min(1, Math.sqrt(sum / playback.samples.length) * 2)
  }, [])

  useEffect(() => {
    const resume = () => {
      const context = playbackRef.current?.context
      if (context?.state === 'suspended') {
        void context.resume().catch((error) => console.warn('Could not resume exam audio:', error))
      }
    }
    window.addEventListener('pointerdown', resume)
    window.addEventListener('keydown', resume)
    return () => {
      window.removeEventListener('pointerdown', resume)
      window.removeEventListener('keydown', resume)
      const playback = playbackRef.current
      playbackRef.current = null
      if (!playback) return
      playback.disposed = true
      for (const source of playback.sources) {
        source.onended = null
        source.stop()
        source.disconnect()
      }
      playback.sources.clear()
      playback.analyser.disconnect()
      void playback.context.close().catch((error) => console.warn('Could not close exam audio:', error))
    }
  }, [])

  return { playAudio, stopAudio, getOutputVolume }
}
