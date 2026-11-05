/** What the particles gather into. */
export type ShapeId = 'sphere' | 'wave'

export const DEFAULT_SHAPE: ShapeId = 'sphere'

export const SHAPES: { id: ShapeId; name: string }[] = [
  { id: 'sphere', name: 'Sphere' },
  { id: 'wave', name: 'Sound wave' },
]

export function isShapeId(value: unknown): value is ShapeId {
  return SHAPES.some((s) => s.id === value)
}
