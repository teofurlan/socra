import { describe, it, expect } from 'vitest'
import { sceneKey, visibleCodeViews, visibleShapeViews } from './scene'
import type { SceneObject } from '@/types/scene'

const objects: SceneObject[] = [
  { id: 'a', primitive: 'code', params: { code: 'x = 1', language: 'python' }, hidden: false },
  { id: 'b', primitive: 'code', params: { code: 'y = 2' }, hidden: true },
  { id: 'c', primitive: 'hologram', params: {}, hidden: false },
  { id: 'cube', primitive: 'shape', params: { shape: 'cube', wireframe: true }, hidden: false },
  { id: 'sphere', primitive: 'shape', params: { shape: 'sphere' }, hidden: true },
]

describe('visibleShapeViews', () => {
  it('shows non-hidden shape objects before the first step', () => {
    expect(visibleShapeViews(objects, null)).toEqual([
      { id: 'cube', shape: 'cube', wireframe: true, rx: 0, ry: 0, rz: 0 },
    ])
  })

  it('updates shape state, rotation and visibility per step', () => {
    const state = {
      cube: { visible: false },
      sphere: { visible: true, rx: 0.5, ry: 0.25, rz: 0 },
    }
    expect(visibleShapeViews(objects, state)).toEqual([
      { id: 'sphere', shape: 'sphere', wireframe: false, rx: 0.5, ry: 0.25, rz: 0 },
    ])
  })
})

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

describe('sceneKey', () => {
  it('changes with the code, not only with the ids', () => {
    const other: SceneObject[] = [{ ...objects[0], params: { code: 'x = 2', language: 'python' } }]
    expect(sceneKey('', objects.slice(0, 1))).not.toBe(sceneKey('', other))
    expect(sceneKey('', other)).toBe(sceneKey('', other))
  })
})
