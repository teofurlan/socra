import { describe, it, expect } from 'vitest'
import { SOLID_KINDS, applyMatrix, idleTurn, isSide, sampleSolid, solidMatrix, type SolidKind } from './solidShapes'

const near = (a: number, b: number, eps = 1e-9) => Math.abs(a - b) < eps

describe('sampleSolid', () => {
  for (const kind of SOLID_KINDS) {
    for (const wireframe of [false, true]) {
      describe(`${kind}${wireframe ? ' wireframe' : ' surface'}`, () => {
        it('returns exactly the count asked for, the same every time', () => {
          for (const count of [1, 7, 280, 1000]) expect(sampleSolid(kind, wireframe, count)).toHaveLength(count)
          expect(sampleSolid(kind, wireframe, 300)).toEqual(sampleSolid(kind, wireframe, 300))
        })

        it('keeps every point inside the unit sphere and gives unit normals', () => {
          for (const p of sampleSolid(kind, wireframe, 600)) {
            expect(Math.hypot(p.x, p.y, p.z)).toBeLessThanOrEqual(1)
            expect(near(Math.hypot(p.nx, p.ny, p.nz), 1, 1e-6)).toBe(true)
          }
        })

        it('spreads over the whole solid, not one corner', () => {
          const points = sampleSolid(kind, wireframe, 600)
          const extent = (f: (p: (typeof points)[number]) => number) => Math.max(...points.map(f)) - Math.min(...points.map(f))
          expect(extent((p) => p.x)).toBeGreaterThan(0.9)
          expect(extent((p) => p.z)).toBeGreaterThan(0.9)
          expect(extent((p) => p.y)).toBeGreaterThan(0.4)
        })
      })
    }
  }

  it('returns nothing for a count of zero or less', () => {
    expect(sampleSolid('cube', false, 0)).toEqual([])
    expect(sampleSolid('cube', false, -3)).toEqual([])
  })

  it('puts cube surface points on a face and wireframe points on an edge', () => {
    const onFace = (p: { x: number; y: number; z: number }) => [p.x, p.y, p.z].filter((c) => near(Math.abs(c), 0.57)).length
    expect(sampleSolid('cube', false, 400).every((p) => onFace(p) >= 1)).toBe(true)
    expect(sampleSolid('cube', false, 400).some((p) => onFace(p) === 1)).toBe(true)
    expect(sampleSolid('cube', true, 400).every((p) => onFace(p) === 2 || onFace(p) === 3)).toBe(true)
  })

  it('puts a sphere on its radius, a torus on its tube and a cylinder inside its radius', () => {
    for (const p of sampleSolid('sphere', false, 200)) expect(near(Math.hypot(p.x, p.y, p.z), 0.85, 1e-9)).toBe(true)
    for (const p of sampleSolid('torus', false, 200)) {
      expect(near(Math.hypot(Math.hypot(p.x, p.z) - 0.62, p.y), 0.26, 1e-6)).toBe(true)
    }
    for (const p of sampleSolid('cylinder', false, 200)) expect(Math.hypot(p.x, p.z)).toBeLessThanOrEqual(0.6 + 1e-9)
  })

  it('narrows a cone toward its apex, which is up on screen', () => {
    const points = sampleSolid('cone', false, 600)
    const top = points.filter((p) => p.y < -0.3)
    const bottom = points.filter((p) => p.y > 0.3)
    const radius = (list: typeof points) => Math.max(...list.map((p) => Math.hypot(p.x, p.z)))
    expect(radius(top)).toBeLessThan(radius(bottom) / 2 + 0.05)
  })

  it('shares points among faces by area: a cylinder side gets about twice the caps', () => {
    const points = sampleSolid('cylinder', false, 900)
    const caps = points.filter((p) => near(Math.abs(p.y), 0.6) && p.ny !== 0).length
    expect(caps).toBeGreaterThan(280)
    expect(caps).toBeLessThan(320)
  })

  it('keeps coverage when a stride picks every few points (fewer particles than points)', () => {
    for (const kind of ['torus', 'cone', 'cube'] as SolidKind[]) {
      const all = sampleSolid(kind, false, 1200)
      const some = all.filter((_, i) => i % 4 === 0)
      const span = (list: typeof all) => Math.max(...list.map((p) => p.x)) - Math.min(...list.map((p) => p.x))
      expect(span(some)).toBeGreaterThan(span(all) * 0.95)
    }
  })
})

describe('solidMatrix', () => {
  it('is a rotation: it keeps lengths', () => {
    const m = solidMatrix({ rx: 0.35, ry: 0.25, rz: 0.1 }, 1.3)
    const [x, y, z] = applyMatrix(m, 0.3, -0.4, 0.5)
    expect(near(Math.hypot(x, y, z), Math.hypot(0.3, -0.4, 0.5), 1e-9)).toBe(true)
  })

  it('depends only on the pose and idle angle, so going back gives back the earlier pose', () => {
    const before = solidMatrix({ rx: 0.1, ry: 0.2, rz: 0 }, 2)
    solidMatrix({ rx: 0.5, ry: 0.5, rz: 0.5 }, 5) // a later step
    expect(solidMatrix({ rx: 0.1, ry: 0.2, rz: 0 }, 2)).toEqual(before)
  })

  it('turns when the scene rotates and when time passes', () => {
    const base = solidMatrix({ rx: 0, ry: 0, rz: 0 }, 0)
    expect(solidMatrix({ rx: 0.25, ry: 0, rz: 0 }, 0)).not.toEqual(base)
    expect(solidMatrix({ rx: 0, ry: 0, rz: 0 }, 1)).not.toEqual(base)
  })

  it('treats a full turn as no turn', () => {
    const a = solidMatrix({ rx: 1, ry: 0, rz: 0 }, 0)
    const b = solidMatrix({ rx: 0, ry: 0, rz: 0 }, 0)
    a.forEach((v, i) => expect(near(v, b[i], 1e-9)).toBe(true))
  })
})

describe('idleTurn', () => {
  it('advances with time and holds still under reduced motion', () => {
    expect(idleTurn(10, false)).toBeGreaterThan(idleTurn(5, false))
    expect(idleTurn(10, true)).toBe(0)
    expect(idleTurn(99, true)).toBe(0)
  })
})

describe('isSide', () => {
  it('paints what faces the viewer as front, and the edge-on and far surfaces as side', () => {
    expect(isSide(-1)).toBe(false)
    expect(isSide(-0.5)).toBe(false)
    expect(isSide(-0.1)).toBe(true)
    expect(isSide(0)).toBe(true)
    expect(isSide(0.9)).toBe(true)
  })

  it('tags a sphere: a front cap in the main colour, the rest in the second', () => {
    const m = solidMatrix({ rx: 0, ry: 0, rz: 0 }, 0)
    const tags = sampleSolid('sphere', false, 800).map((p) => isSide(applyMatrix(m, p.nx, p.ny, p.nz)[2]))
    const sides = tags.filter(Boolean).length
    // A cap with z <= -0.3 covers (1 - 0.3) / 2 of a sphere's area.
    expect(sides / tags.length).toBeGreaterThan(0.6)
    expect(sides / tags.length).toBeLessThan(0.7)
  })
})
