import { useSyncExternalStore } from 'react'

const REDUCED_QUERY = '(prefers-reduced-motion: reduce)'

function subscribe(notify: () => void): () => void {
  const query = typeof window !== 'undefined' ? window.matchMedia?.(REDUCED_QUERY) : undefined
  query?.addEventListener?.('change', notify)
  return () => query?.removeEventListener?.('change', notify)
}

function reducedNow(): boolean {
  return typeof window !== 'undefined' && (window.matchMedia?.(REDUCED_QUERY).matches ?? false)
}

/** Follows the user's reduced-motion preference, also when it changes while something is drawn. */
export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribe, reducedNow, () => false)
}
