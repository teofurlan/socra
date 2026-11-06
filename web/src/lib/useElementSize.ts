import { useEffect, useRef, useState, type RefObject } from 'react'

export interface Size {
  width: number
  height: number
}

/**
 * The content size of an element, kept current; `fallback` stands in before it is measured or without
 * ResizeObserver. The observer follows the element the ref holds now, also when it mounts later than
 * the first render or is replaced by another one.
 */
export function useElementSize(ref: RefObject<HTMLElement | null>, fallback: Size): Size {
  const [size, setSize] = useState(fallback)
  const watched = useRef<{ element: HTMLElement; observer: ResizeObserver } | null>(null)
  // A ref change does not render, so look at the ref after every render and re-observe only when it differs.
  useEffect(() => {
    const element = ref.current
    if (watched.current?.element === element) return
    watched.current?.observer.disconnect()
    watched.current = null
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[entries.length - 1]?.contentRect
      if (rect && rect.width > 0 && rect.height > 0) setSize((old) => (old.width === rect.width && old.height === rect.height ? old : { width: rect.width, height: rect.height }))
    })
    observer.observe(element)
    watched.current = { element, observer }
  })
  useEffect(
    () => () => {
      watched.current?.observer.disconnect()
      watched.current = null
    },
    [],
  )
  return size
}
