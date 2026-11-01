import { renderHook, act } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FakeAudioContext } from '@/test/fakeSocket'
import { useExamAudio } from './useExamAudio'

const CLIP = btoa('RIFF')

async function flush() {
  await act(async () => {
    await Promise.resolve()
    await Promise.resolve()
  })
}

describe('useExamAudio keep-alive', () => {
  beforeEach(() => {
    FakeAudioContext.instances = []
    vi.stubGlobal('AudioContext', FakeAudioContext)
  })
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the output fed with an inaudible signal so the first words are not lost', async () => {
    const { result } = renderHook(() => useExamAudio())
    act(() => result.current.playAudio(CLIP))
    await flush()

    const context = FakeAudioContext.latest()
    expect(context.constantSources).toHaveLength(1)
    const keepAlive = context.constantSources[0]
    expect(keepAlive.offset.value).toBeGreaterThan(0)
    expect(keepAlive.offset.value).toBeLessThanOrEqual(0.001)
    expect(keepAlive.connect).toHaveBeenCalledWith(context.destination)
    expect(keepAlive.connect).not.toHaveBeenCalledWith(context.analyser)
    expect(keepAlive.start).toHaveBeenCalledTimes(1)
  })

  it('starts one keep-alive per context, not one per clip, and still plays every clip', async () => {
    const { result } = renderHook(() => useExamAudio())
    act(() => result.current.playAudio(CLIP))
    act(() => result.current.playAudio(CLIP))
    await flush()
    await flush()

    const context = FakeAudioContext.latest()
    expect(context.constantSources).toHaveLength(1)
    expect(context.sources).toHaveLength(2)
    expect(context.sources[0].start).toHaveBeenCalledWith(2)
    expect(context.sources[1].start).toHaveBeenCalledWith(2.25)
  })

  it('stopAudio silences clips but keeps the output awake', async () => {
    const { result } = renderHook(() => useExamAudio())
    act(() => result.current.playAudio(CLIP))
    await flush()
    act(() => result.current.stopAudio())

    const context = FakeAudioContext.latest()
    expect(context.sources[0].stop).toHaveBeenCalled()
    expect(context.constantSources[0].stop).not.toHaveBeenCalled()
  })

  it('stops the keep-alive when the hook unmounts', async () => {
    const { result, unmount } = renderHook(() => useExamAudio())
    act(() => result.current.playAudio(CLIP))
    await flush()
    unmount()

    const context = FakeAudioContext.latest()
    expect(context.constantSources[0].stop).toHaveBeenCalled()
    expect(context.constantSources[0].disconnect).toHaveBeenCalled()
    expect(context.close).toHaveBeenCalled()
  })
})
