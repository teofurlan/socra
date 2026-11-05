import { describe, it, expect, beforeEach, vi } from 'vitest'
import {
  getStoredTurnMode,
  setStoredTurnMode,
  STORAGE_KEY_MODE,
  getStoredMicDeviceId,
  setStoredMicDeviceId,
  STORAGE_KEY_MIC_DEVICE,
  getStoredShape,
  setStoredShape,
  STORAGE_KEY_SHAPE,
  getStoredVoice,
  setStoredVoice,
  STORAGE_KEY_VOICE,
  setStoredSilenceTimeout,
  STORAGE_KEY_SILENCE_TIMEOUT,
  setStoredOrbPalette,
  STORAGE_KEY_ORB_PALETTE,
  setStoredAgentSelection,
  STORAGE_KEY_AGENT_SELECTION,
  setStoredAgentFolder,
  STORAGE_KEY_AGENT_FOLDER,
  SHARED_PREFERENCE_KEYS,
} from './storage'
import { setStoredTheme, STORAGE_KEY_THEME } from './theme'
import { sharePreference } from './preferences'

vi.mock('./preferences', () => ({ sharePreference: vi.fn() }))

describe('storage (turn mode persistence)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to auto when localStorage is empty', () => {
    expect(getStoredTurnMode()).toBe('auto')
  })

  it('persists mode change to localStorage and retrieves it', () => {
    setStoredTurnMode('push-to-talk')
    expect(window.localStorage.getItem(STORAGE_KEY_MODE)).toBe('push-to-talk')
    expect(getStoredTurnMode()).toBe('push-to-talk')

    setStoredTurnMode('auto')
    expect(window.localStorage.getItem(STORAGE_KEY_MODE)).toBe('auto')
    expect(getStoredTurnMode()).toBe('auto')
  })

  it('safely handles localStorage throwing exceptions', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('Access denied')
    })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('Quota exceeded')
    })

    // Should not throw, should fallback to default mode
    expect(() => setStoredTurnMode('push-to-talk')).not.toThrow()
    expect(getStoredTurnMode('auto')).toBe('auto')
  })

  it('returns default mode when stored value is invalid', () => {
    window.localStorage.setItem(STORAGE_KEY_MODE, 'invalid-mode')
    expect(getStoredTurnMode('auto')).toBe('auto')
  })
})

describe('storage (microphone selection)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to the system default microphone', () => {
    expect(getStoredMicDeviceId()).toBe('')
  })

  it('persists the selected microphone across reloads', () => {
    setStoredMicDeviceId('usb-mic')
    expect(window.localStorage.getItem(STORAGE_KEY_MIC_DEVICE)).toBe('usb-mic')
    expect(getStoredMicDeviceId()).toBe('usb-mic')
  })

  it('does not throw when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => setStoredMicDeviceId('usb-mic')).not.toThrow()
    expect(getStoredMicDeviceId()).toBe('')
  })
})

describe('storage (retired particle looks)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it.each(['particle-lines', 'particle-letters', 'particle-grid', 'orb', 'hologram'])(
    'leaves other preferences intact when a stored look value %s is still there',
    (look) => {
      window.localStorage.setItem('socra_visualizer', look)
      setStoredShape('wave')
      expect(() => getStoredShape()).not.toThrow()
      expect(getStoredShape()).toBe('wave')
      expect(SHARED_PREFERENCE_KEYS).not.toContain('socra_visualizer')
    },
  )
})

describe('storage (particle shape)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to the sphere when nothing is stored', () => {
    expect(getStoredShape()).toBe('sphere')
  })

  it('persists the sound wave and reads it back', () => {
    setStoredShape('wave')
    expect(window.localStorage.getItem(STORAGE_KEY_SHAPE)).toBe('wave')
    expect(getStoredShape()).toBe('wave')
  })

  it('ignores an unknown stored value', () => {
    window.localStorage.setItem(STORAGE_KEY_SHAPE, 'cube')
    expect(getStoredShape()).toBe('sphere')
  })
})

describe('storage (voice selection)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('defaults to null when nothing is stored', () => {
    expect(getStoredVoice()).toBeNull()
  })

  it('persists the voice and reads it back', () => {
    setStoredVoice('alex-dora')
    expect(window.localStorage.getItem(STORAGE_KEY_VOICE)).toBe('alex-dora')
    expect(getStoredVoice()).toBe('alex-dora')
  })

  it('does not throw when localStorage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => setStoredVoice('alex-dora')).not.toThrow()
    expect(getStoredVoice()).toBeNull()
  })
})


describe('storage (shared across page origins, #27)', () => {
  beforeEach(() => {
    window.localStorage.clear()
    vi.mocked(sharePreference).mockClear()
  })

  it('sends each preference change to the shared store', () => {
    setStoredTurnMode('push-to-talk')
    setStoredSilenceTimeout(2000)
    setStoredOrbPalette('ember')
    setStoredShape('wave')
    setStoredAgentSelection({ backend: 'pi', model: 'm' })
    setStoredAgentFolder('C:/work')
    setStoredVoice('dora')
    setStoredTheme('light')

    expect(vi.mocked(sharePreference).mock.calls).toEqual([
      [STORAGE_KEY_MODE, 'push-to-talk'],
      [STORAGE_KEY_SILENCE_TIMEOUT, '2000'],
      [STORAGE_KEY_ORB_PALETTE, 'ember'],
      [STORAGE_KEY_SHAPE, 'wave'],
      [STORAGE_KEY_AGENT_SELECTION, JSON.stringify({ backend: 'pi', model: 'm' })],
      [STORAGE_KEY_AGENT_FOLDER, 'C:/work'],
      [STORAGE_KEY_VOICE, 'dora'],
      [STORAGE_KEY_THEME, 'light'],
    ])
    expect([...SHARED_PREFERENCE_KEYS].sort()).toEqual(
      vi.mocked(sharePreference).mock.calls.map(([key]) => key).sort(),
    )
  })

  it('keeps the microphone on this origin: browsers scope device ids per origin', () => {
    setStoredMicDeviceId('mic-1')
    expect(sharePreference).not.toHaveBeenCalled()
    expect(SHARED_PREFERENCE_KEYS).not.toContain(STORAGE_KEY_MIC_DEVICE)
  })
})
