import type { WalkthroughData, WalkthroughMessage } from '@/types/exam'

/** The scene after one of its messages; steps and status without a scene change nothing. */
export function reduceWalkthrough(current: WalkthroughData | null, message: WalkthroughMessage): WalkthroughData | null {
  switch (message.type) {
    case 'walkthrough':
      return { title: message.title, objects: message.objects, total: message.total, step: null, status: 'playing', reason: null }
    case 'walkthrough_step': {
      if (!current) return current
      const { index, total, id, say, state } = message
      return { ...current, step: { index, total, id, say, state } }
    }
    case 'walkthrough_status':
      if (!current) return current
      return { ...current, status: message.status, reason: message.reason ?? null }
  }
}
