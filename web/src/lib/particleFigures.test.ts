import { describe, it, expect } from 'vitest'
import { outlinePoints, pointsFromMask, type Mask } from './particleFigures'

/** A mask with one opaque rectangle, as a canvas would return it (RGBA bytes). */
function maskWithBlock(width: number, height: number, block: { x0: number; y0: number; x1: number; y1: number }): Mask {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let y = block.y0; y < block.y1; y++) {
    for (let x = block.x0; x < block.x1; x++) data[(y * width + x) * 4 + 3] = 255
  }
  return { width, height, data }
}

describe('pointsFromMask', () => {
  const mask = maskWithBlock(200, 50, { x0: 20, y0: 10, x1: 120, y1: 40 })

  it('places every point on an opaque pixel, normalised to the mask', () => {
    const points = pointsFromMask(mask, 300)
    expect(points.length).toBeGreaterThan(100)
    for (const q of points) {
      expect(q.x * mask.width).toBeGreaterThanOrEqual(20 - 1)
      expect(q.x * mask.width).toBeLessThanOrEqual(120 + 1)
      expect(q.y * mask.height).toBeGreaterThanOrEqual(10 - 1)
      expect(q.y * mask.height).toBeLessThanOrEqual(40 + 1)
    }
  })

  it('never returns more than the requested number of points and still covers the whole shape', () => {
    const points = pointsFromMask(mask, 80)
    expect(points.length).toBeLessThanOrEqual(80)
    expect(points.length).toBeGreaterThan(40)
    expect(Math.min(...points.map((q) => q.x * mask.width))).toBeLessThan(30)
    expect(Math.max(...points.map((q) => q.x * mask.width))).toBeGreaterThan(110)
  })

  it('returns the same points for the same mask', () => {
    expect(pointsFromMask(mask, 120)).toEqual(pointsFromMask(mask, 120))
  })

  it('returns no points for an empty mask or no budget', () => {
    expect(pointsFromMask(maskWithBlock(40, 40, { x0: 0, y0: 0, x1: 0, y1: 0 }), 100)).toEqual([])
    expect(pointsFromMask(mask, 0)).toEqual([])
  })
})

describe('outlinePoints', () => {
  it('returns the requested number of points, all on the edge of the box', () => {
    const points = outlinePoints(48, 300, 60)
    expect(points).toHaveLength(48)
    for (const q of points) {
      const onEdge = q.x === 0 || q.x === 1 || q.y === 0 || q.y === 1
      expect(onEdge).toBe(true)
    }
  })

  it('spaces the points evenly in pixels, so a wide box gets more of them along its long sides', () => {
    const points = outlinePoints(72, 300, 60)
    const horizontal = points.filter((q) => (q.y === 0 || q.y === 1) && q.x > 0 && q.x < 1)
    const vertical = points.filter((q) => (q.x === 0 || q.x === 1) && q.y > 0 && q.y < 1)
    expect(horizontal.length).toBeGreaterThan(vertical.length * 3)
  })

  it('lays lines along the edge they sit on', () => {
    for (const q of outlinePoints(40, 200, 100)) {
      if (q.y === 0 || q.y === 1) expect(q.a).toBe(0)
      else expect(q.a).toBeCloseTo(Math.PI / 2, 6)
    }
  })

  it('returns no points for no budget', () => {
    expect(outlinePoints(0, 100, 100)).toEqual([])
  })
})
