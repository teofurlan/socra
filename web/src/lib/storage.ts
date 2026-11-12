import type { TurnMode } from '@/types/exam'
import type { AgentSelection } from '@/types/agent'
import { sharePreference } from '@/lib/preferences'
import { STORAGE_KEY_THEME } from '@/lib/theme'
import {
  DEFAULT_SHAPE,
  isShapeId,
  type ShapeId,
} from '@/components/visualizers'

export const STORAGE_KEY_MODE = 'oral_exam_turn_mode'
export const STORAGE_KEY_SILENCE_TIMEOUT = 'oral_exam_silence_timeout_ms'

export const STORAGE_KEY_ORB_PALETTE = 'socra_orb_palette'
export const STORAGE_KEY_REVIEW_DICTATION = 'socra_review_dictation'

export const DEFAULT_SILENCE_TIMEOUT_MS = 3000
export const MIN_SILENCE_TIMEOUT_MS = 500
export const MAX_SILENCE_TIMEOUT_MS = 10_000

export function getStoredTurnMode(defaultMode: TurnMode = 'auto'): TurnMode {
  try {
    const item = window.localStorage.getItem(STORAGE_KEY_MODE)
    if (item === 'auto' || item === 'push-to-talk') {
      return item
    }
  } catch (err) {
    console.warn('Failed to read turn mode from localStorage:', err)
  }
  return defaultMode
}

export function setStoredTurnMode(mode: TurnMode): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_MODE, mode)
  } catch (err) {
    console.warn('Failed to write turn mode to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_MODE, mode)
}

export function getStoredSilenceTimeout(): number {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_SILENCE_TIMEOUT)
    if (raw !== null) {
      const parsed = Number(raw)
      if (Number.isFinite(parsed) && parsed >= MIN_SILENCE_TIMEOUT_MS && parsed <= MAX_SILENCE_TIMEOUT_MS) {
        return parsed
      }
    }
  } catch (err) {
    console.warn('Failed to read silence timeout from localStorage:', err)
  }
  return DEFAULT_SILENCE_TIMEOUT_MS
}

export function setStoredSilenceTimeout(ms: number): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_SILENCE_TIMEOUT, String(ms))
  } catch (err) {
    console.warn('Failed to write silence timeout to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_SILENCE_TIMEOUT, String(ms))
}

/** 'state' = colours follow the protocol state; otherwise a palette id. */
export function getStoredOrbPalette(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY_ORB_PALETTE) || 'state'
  } catch (err) {
    console.warn('Failed to read orb palette from localStorage:', err)
    return 'state'
  }
}

export function setStoredOrbPalette(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_ORB_PALETTE, id)
  } catch (err) {
    console.warn('Failed to write orb palette to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_ORB_PALETTE, id)
}

export const STORAGE_KEY_SHAPE = 'socra_shape'

export function getStoredShape(): ShapeId {
  try {
    const item = window.localStorage.getItem(STORAGE_KEY_SHAPE)
    if (isShapeId(item)) return item
  } catch (err) {
    console.warn('Failed to read particle shape from localStorage:', err)
  }
  return DEFAULT_SHAPE
}

export function setStoredShape(id: ShapeId): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_SHAPE, id)
  } catch (err) {
    console.warn('Failed to write particle shape to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_SHAPE, id)
}

export const STORAGE_KEY_MIC_DEVICE = 'socra_mic_device_id'

/** '' = the system default microphone; otherwise a MediaDeviceInfo.deviceId. */
export function getStoredMicDeviceId(): string {
  try {
    return window.localStorage.getItem(STORAGE_KEY_MIC_DEVICE) ?? ''
  } catch (err) {
    console.warn('Failed to read microphone from localStorage:', err)
    return ''
  }
}

export function setStoredMicDeviceId(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_MIC_DEVICE, id)
  } catch (err) {
    console.warn('Failed to write microphone to localStorage:', err)
  }
}

export const STORAGE_KEY_AGENT_SELECTION = 'socra_agent_selection'
export const STORAGE_KEY_AGENT_FOLDER = 'socra_agent_folder'

export function getStoredAgentSelection(): AgentSelection | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY_AGENT_SELECTION)
    if (raw === null) return null
    const parsed: unknown = JSON.parse(raw)
    if (
      typeof parsed === 'object' && parsed !== null &&
      typeof (parsed as AgentSelection).backend === 'string' &&
      typeof (parsed as AgentSelection).model === 'string'
    ) {
      const { backend, model } = parsed as AgentSelection
      return { backend, model }
    }
  } catch (err) {
    console.warn('Failed to read agent selection from localStorage:', err)
  }
  return null
}

export function setStoredAgentSelection(selection: AgentSelection): void {
  const value = JSON.stringify(selection)
  try {
    window.localStorage.setItem(STORAGE_KEY_AGENT_SELECTION, value)
  } catch (err) {
    console.warn('Failed to write agent selection to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_AGENT_SELECTION, value)
}

export function getStoredAgentFolder(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY_AGENT_FOLDER) || null
  } catch (err) {
    console.warn('Failed to read agent folder from localStorage:', err)
    return null
  }
}

export function setStoredAgentFolder(path: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_AGENT_FOLDER, path)
  } catch (err) {
    console.warn('Failed to write agent folder to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_AGENT_FOLDER, path)
}

export const STORAGE_KEY_VOICE = 'socra_voice'

export function getStoredVoice(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY_VOICE) || null
  } catch (err) {
    console.warn('Failed to read voice from localStorage:', err)
    return null
  }
}

export function setStoredVoice(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_VOICE, id)
  } catch (err) {
    console.warn('Failed to write voice to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_VOICE, id)
}

/** Whether a spoken turn is shown in the composer for the user to send, not sent at once. */
export function getStoredReviewDictation(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY_REVIEW_DICTATION) === 'true'
  } catch (err) {
    console.warn('Failed to read review dictation from localStorage:', err)
  }
  return false
}

export function setStoredReviewDictation(review: boolean): void {
  try {
    window.localStorage.setItem(STORAGE_KEY_REVIEW_DICTATION, String(review))
  } catch (err) {
    console.warn('Failed to write review dictation to localStorage:', err)
  }
  sharePreference(STORAGE_KEY_REVIEW_DICTATION, String(review))
}

/**
 * Preferences kept by the Socra server for every page origin (#27). The
 * microphone stays per origin: browsers give each origin its own device ids.
 */
export const SHARED_PREFERENCE_KEYS: readonly string[] = [
  STORAGE_KEY_MODE,
  STORAGE_KEY_SILENCE_TIMEOUT,
  STORAGE_KEY_ORB_PALETTE,
  STORAGE_KEY_SHAPE,
  STORAGE_KEY_AGENT_SELECTION,
  STORAGE_KEY_AGENT_FOLDER,
  STORAGE_KEY_VOICE,
  STORAGE_KEY_THEME,
  STORAGE_KEY_REVIEW_DICTATION,
]
