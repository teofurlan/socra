import { describe, it, expect } from 'vitest'
import { visibleCodeViews } from './scene'
import type { SceneObject } from '@/types/scene'

const objects: SceneObject[] = [
  { id: 'a', primitive: 'code', params: { code: 'x = 1', language: 'python' }, hidden: false },
  { id: 'b', primitive: 'code', params: { code: 'y = 2' }, hidden: true },
  { id: 'c', primitive: 'diagram', params: {}, hidden: false },
]

describe('visibleCodeViews', () => {
  it('before the first step shows every object that does not start hidden', () => {
    expect(visibleCodeViews(objects, null)).toEqual([{ id: 'a', code: 'x = 1', language: 'python', focus: null }])
  })

  it('follows the visibility and focus of the current step', () => {
    const state = { a: { visible: false, lines: null }, b: { visible: true, lines: [1, 1] }, c: { visible: true } }
    expect(visibleCodeViews(objects, state)).toEqual([{ id: 'b', code: 'y = 2', language: '', focus: [1, 1] }])
  })

  it('skips primitives it cannot draw and malformed params', () => {
    const odd: SceneObject[] = [{ id: 'z', primitive: 'code', params: { code: 3 }, hidden: false }]
    expect(visibleCodeViews(odd, null)).toEqual([])
  })
})
