import { useEffect, useState, type RefObject } from 'react'

export interface Size {
  width: number
  height: number
}

/** The content size of an element, kept current; `fallback` stands in before it is measured or without ResizeObserver. */
export function useElementSize(ref: RefObject<HTMLElement | null>, fallback: Size): Size {
  const [size, setSize] = useState(fallback)
  useEffect(() => {
    const element = ref.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver((entries) => {
      const rect = entries[entries.length - 1]?.contentRect
      if (rect && rect.width > 0 && rect.height > 0) setSize((old) => (old.width === rect.width && old.height === rect.height ? old : { width: rect.width, height: rect.height }))
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref])
  return size
}
