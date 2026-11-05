import { describe, it, expect } from 'vitest'
import { FIGURE_SHARE, ParticleField, headlineDotScale, fibonacciSphere, particleCount, type Figure, type FieldFrame } from './particleField'

/** Small deterministic PRNG so the physics runs the same way every time. */
function seeded(seed = 1) {
  let s = seed
  return () => {
    s = (s * 16807) % 2147483647
    return (s - 1) / 2147483646
  }
}

const BASE: Omit<FieldFrame, 'state' | 'volume' | 'time'> = {
  dt: 1 / 60,
  width: 800,
  height: 600,
  cx: 400,
  cy: 300,
  radius: 100,
  reducedMotion: false,
}

function run(field: ParticleField, state: FieldFrame['state'], seconds: number, start: number) {
  let time = start
  for (let i = 0; i < seconds * 60; i++) {
    time += BASE.dt
    field.step({ ...BASE, state, volume: state === 'idle' ? 0 : 0.5, time })
  }
  return time
}

function meanDistance(field: ParticleField) {
  const ps = field.particles
  return ps.reduce((sum, p) => sum + Math.hypot(p.x - BASE.cx, p.y - BASE.cy), 0) / ps.length
}

describe('fibonacciSphere', () => {
  it('returns the requested number of points, all on the unit sphere', () => {
    const points = fibonacciSphere(500)
    expect(points).toHaveLength(500)
    for (const p of points) expect(Math.hypot(p.x, p.y, p.z)).toBeCloseTo(1, 6)
  })
})

describe('particleCount', () => {
  it('scales with the screen area within fixed bounds', () => {
    expect(particleCount(375, 812)).toBeLessThan(particleCount(1440, 900))
    expect(particleCount(10, 10)).toBeGreaterThanOrEqual(400)
    expect(particleCount(10_000, 10_000)).toBeLessThanOrEqual(1800)
  })
})

describe('ParticleField', () => {
  it('stays scattered while idle, gathers into the sphere for a voice, and scatters again', () => {
    const field = new ParticleField({ count: 400, random: seeded(7) })
    field.resize(BASE.width, BASE.height)

    let t = run(field, 'idle', 2, 0)
    expect(meanDistance(field)).toBeGreaterThan(180)

    t = run(field, 'speaking', 4, t)
    const gathered = meanDistance(field)
    expect(gathered).toBeGreaterThan(BASE.radius * 0.5)
    expect(gathered).toBeLessThan(BASE.radius * 1.3)

    run(field, 'idle', 6, t)
    expect(meanDistance(field)).toBeGreaterThan(180)
  })

  it('also gathers while listening and thinking', () => {
    for (const state of ['listening', 'thinking'] as const) {
      const field = new ParticleField({ count: 300, random: seeded(3) })
      field.resize(BASE.width, BASE.height)
      run(field, state, 4, 0)
      expect(meanDistance(field)).toBeLessThan(BASE.radius * 1.3)
    }
  })

  it('adds light on a dark page and paints normally on a light one', () => {
    const modes = (light: boolean) => {
      const field = new ParticleField({ count: 20, random: seeded(2) })
      field.resize(BASE.width, BASE.height)
      field.setLightBackground(light)
      const seen: string[] = []
      const ctx = {
        setTransform: () => {},
        clearRect: () => {},
        beginPath: () => {},
        arc: () => {},
        fill(this: { globalCompositeOperation: string }) {
          seen.push(this.globalCompositeOperation)
        },
        globalCompositeOperation: 'source-over',
      } as unknown as CanvasRenderingContext2D
      field.draw(ctx, 1)
      return new Set(seen)
    }
    expect(modes(false)).toEqual(new Set(['lighter']))
    expect(modes(true)).toEqual(new Set(['source-over']))
  })

  it('starts scattered over the first screen size instead of piled in the corner', () => {
    const field = new ParticleField({ count: 300, random: seeded(3) })
    field.resize(BASE.width, BASE.height)

    const xs = field.particles.map((p) => p.x)
    const ys = field.particles.map((p) => p.y)
    expect(Math.max(...xs)).toBeGreaterThan(BASE.width * 0.8)
    expect(Math.max(...ys)).toBeGreaterThan(BASE.height * 0.8)
  })

  it('draws one round dot per particle, free in the plane, sized by the particle', () => {
    const field = new ParticleField({ count: 60, random: seeded(5) })
    field.resize(BASE.width, BASE.height)
    run(field, 'speaking', 1, 0)
    const dots: { x: number; y: number; r: number }[] = []
    const ctx = {
      setTransform: () => {},
      clearRect: () => {},
      beginPath: () => {},
      arc: (x: number, y: number, r: number) => dots.push({ x, y, r }),
      fill: () => {},
    } as unknown as CanvasRenderingContext2D
    field.draw(ctx, 1)
    expect(dots).toHaveLength(60)
    field.particles.forEach((p, i) => {
      expect(dots[i]).toEqual({ x: p.x, y: p.y, r: 0.6 + p.size * 0.16 })
    })
  })

  it('gathers into a wide band of strands for the sound wave, the sphere staying round', () => {
    const spread = (shape: 'sphere' | 'wave') => {
      const field = new ParticleField({ count: 400, shape, random: seeded(9) })
      field.resize(BASE.width, BASE.height)
      run(field, 'speaking', 4, 0)
      const dx = field.particles.map((p) => Math.abs(p.x - BASE.cx))
      const dy = field.particles.map((p) => Math.abs(p.y - BASE.cy))
      return { field, dx, dy, w: Math.max(...dx), h: Math.max(...dy) }
    }

    const sphere = spread('sphere')
    expect(sphere.w).toBeLessThan(BASE.radius * 1.5)
    expect(sphere.h).toBeLessThan(BASE.radius * 1.5)

    const wave = spread('wave')
    expect(wave.w).toBeGreaterThan(BASE.radius * 1.8)
    expect(wave.h).toBeLessThan(BASE.radius * 0.9)
    // The strands cross and pinch together at both ends of the wave.
    const ends = wave.field.particles.filter((p) => Math.abs(p.x - BASE.cx) > BASE.radius * 2)
    expect(ends.length).toBeGreaterThan(0)
    for (const p of ends) expect(Math.abs(p.y - BASE.cy)).toBeLessThan(BASE.radius * 0.3)
  })

  it('keeps the wave strands apart while the voice is quiet', () => {
    const field = new ParticleField({ count: 400, shape: 'wave', random: seeded(8) })
    field.resize(BASE.width, BASE.height)
    let time = 0
    for (let i = 0; i < 4 * 60; i++) {
      time += BASE.dt
      field.step({ ...BASE, state: 'speaking', volume: 0, time })
    }
    expect(Math.max(...field.particles.map((p) => Math.abs(p.y - BASE.cy)))).toBeGreaterThan(BASE.radius * 0.12)
  })

  it('places every wave particle on one of five strands', () => {
    const field = new ParticleField({ count: 400, shape: 'wave', random: seeded(4) })
    const strands = new Set(field.particles.map((p) => p.strand))
    expect(strands).toEqual(new Set([0, 1, 2, 3, 4]))
    for (const p of field.particles) {
      expect(p.u).toBeGreaterThanOrEqual(-1)
      expect(p.u).toBeLessThanOrEqual(1)
    }
  })

  it('switches between the sphere and the wave without rebuilding the particles', () => {
    const field = new ParticleField({ count: 300, random: seeded(6) })
    field.resize(BASE.width, BASE.height)
    expect(field.shape).toBe('sphere')
    const before = field.particles
    let t = run(field, 'speaking', 4, 0)

    field.setShape('wave')
    expect(field.particles).toBe(before)
    t = run(field, 'speaking', 3, t)
    expect(Math.max(...field.particles.map((p) => Math.abs(p.x - BASE.cx)))).toBeGreaterThan(BASE.radius * 1.8)

    field.setShape('sphere')
    run(field, 'speaking', 3, t)
    expect(Math.max(...field.particles.map((p) => Math.abs(p.x - BASE.cx)))).toBeLessThan(BASE.radius * 1.5)
  })

  it('gathers into a small calm formation at rest while idle, in either shape', () => {
    for (const shape of ['sphere', 'wave'] as const) {
      const spoken = new ParticleField({ count: 400, shape, random: seeded(12) })
      spoken.resize(BASE.width, BASE.height)
      run(spoken, 'speaking', 4, 0)

      const resting = new ParticleField({ count: 400, shape, random: seeded(12) })
      resting.resize(BASE.width, BASE.height)
      let time = 0
      for (let i = 0; i < 4 * 60; i++) {
        time += BASE.dt
        resting.step({ ...BASE, state: 'idle', volume: 0, time, rest: true })
      }
      // Every particle joins the formation, none left loose over the screen.
      const far = shape === 'sphere' ? BASE.radius * 1.2 : BASE.radius * 2.6
      expect(resting.particles.every((p) => Math.hypot(p.x - BASE.cx, p.y - BASE.cy) < far)).toBe(true)
      expect(meanDistance(resting)).toBeLessThan(meanDistance(spoken))
      // Quieter than a voice: dimmer, and leaning to the first (grey) colour of the idle pair.
      const mean = (f: ParticleField, k: 'alpha' | 'tint') => f.particles.reduce((s, p) => s + p[k], 0) / f.particles.length
      expect(mean(resting, 'alpha')).toBeLessThan(mean(spoken, 'alpha') * 0.75)
      expect(mean(resting, 'tint')).toBeLessThan(0.3)
    }
  })

  it('keeps the rest formation visible on a light ground, where paint does not add up', () => {
    const restingAlpha = (light: boolean) => {
      const field = new ParticleField({ count: 300, random: seeded(14) })
      field.resize(BASE.width, BASE.height)
      field.setLightBackground(light)
      let time = 0
      for (let i = 0; i < 4 * 60; i++) {
        time += BASE.dt
        field.step({ ...BASE, state: 'idle', volume: 0, time, rest: true })
      }
      return field.particles.reduce((s, p) => s + p.alpha, 0) / field.particles.length
    }
    expect(restingAlpha(true)).toBeGreaterThan(restingAlpha(false) * 1.3)
  })

  it('ignores the rest formation once the conversation has a voice', () => {
    const positions = (rest: boolean) => {
      const field = new ParticleField({ count: 200, random: seeded(13) })
      field.resize(BASE.width, BASE.height)
      let time = 0
      for (let i = 0; i < 2 * 60; i++) {
        time += BASE.dt
        field.step({ ...BASE, state: 'speaking', volume: 0.5, time, rest })
      }
      return field.particles.map((p) => [p.x, p.y])
    }
    expect(positions(true)).toEqual(positions(false))
  })

  it('keeps every particle position finite', () => {
    const field = new ParticleField({ count: 200, random: seeded(11) })
    field.resize(BASE.width, BASE.height)
    run(field, 'speaking', 2, 0)
    for (const p of field.particles) {
      expect(Number.isFinite(p.x)).toBe(true)
      expect(Number.isFinite(p.y)).toBe(true)
    }
  })
})

describe('headlineDotScale', () => {
  it('keeps the normal size once about a thousand particles are recruited, and grows below that up to 1.5x', () => {
    expect(headlineDotScale(1260)).toBe(1)
    expect(headlineDotScale(1007)).toBe(1)
    expect(headlineDotScale(500)).toBeCloseTo(Math.SQRT2, 5)
    expect(headlineDotScale(280)).toBe(1.5)
    expect(headlineDotScale(10)).toBe(1.5)
    expect(headlineDotScale(0)).toBe(1)
  })
})

describe('ParticleField figures', () => {
  const BOX = { x: 100, y: 400, w: 200, h: 100 }
  /** A 10 x 6 grid of points inside the box, normalised to 0..1. */
  const GRID = Array.from({ length: 60 }, (_, i) => ({ x: (i % 10) / 9, y: Math.floor(i / 10) / 5 }))

  function runWith(field: ParticleField, state: FieldFrame['state'], seconds: number, start: number, figures: Figure[]) {
    let time = start
    for (let i = 0; i < seconds * 60; i++) {
      time += BASE.dt
      field.step({ ...BASE, state, volume: state === 'idle' ? 0 : 0.5, time, figures })
    }
    return time
  }

  function recruited(field: ParticleField) {
    return field.particles.filter((p) => p.figure >= 0)
  }

  /** Mean distance from each recruited particle to the nearest figure point on screen. */
  function figureError(field: ParticleField, points: { x: number; y: number }[], box = BOX) {
    const ps = recruited(field)
    const onScreen = points.map((q) => ({ x: box.x + q.x * box.w, y: box.y + q.y * box.h }))
    return ps.reduce((sum, p) => sum + Math.min(...onScreen.map((q) => Math.hypot(p.x - q.x, p.y - q.y))), 0) / ps.length
  }

  it('recruits one particle per figure point and settles them on the points inside the box', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    runWith(field, 'speaking', 4, 0, [{ id: 'title', points: GRID, box: BOX, role: 'pointer' }])
    expect(recruited(field)).toHaveLength(GRID.length)
    expect(figureError(field, GRID)).toBeLessThan(12)
  })

  it('keeps the other particles in the voice formation while a pointer figure is shown', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    runWith(field, 'speaking', 4, 0, [{ id: 'title', points: GRID, box: BOX, role: 'pointer' }])
    const rest = field.particles.filter((p) => p.figure < 0)
    const mean = rest.reduce((sum, p) => sum + Math.hypot(p.x - BASE.cx, p.y - BASE.cy), 0) / rest.length
    expect(mean).toBeLessThan(BASE.radius * 1.3)
  })

  it('lets the other particles drift loose while a lead figure takes the stage', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    runWith(field, 'speaking', 5, 0, [{ id: 'title', points: GRID, box: BOX, role: 'lead' }])
    const rest = field.particles.filter((p) => p.figure < 0)
    const mean = rest.reduce((sum, p) => sum + Math.hypot(p.x - BASE.cx, p.y - BASE.cy), 0) / rest.length
    expect(mean).toBeGreaterThan(180)
    expect(figureError(field, GRID)).toBeLessThan(12)
  })

  it('follows its box when the box moves', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    const moved = { ...BOX, x: BOX.x + 150, y: BOX.y - 200 }
    let t = runWith(field, 'speaking', 3, 0, [{ id: 'title', points: GRID, box: BOX, role: 'pointer' }])
    t = runWith(field, 'speaking', 3, t, [{ id: 'title', points: GRID, box: moved, role: 'pointer' }])
    expect(figureError(field, GRID, moved)).toBeLessThan(12)
  })

  it('releases its particles back to the voice formation when the figure goes away', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    const t = runWith(field, 'speaking', 3, 0, [{ id: 'title', points: GRID, box: BOX, role: 'lead' }])
    runWith(field, 'speaking', 4, t, [])
    expect(recruited(field)).toHaveLength(0)
    expect(meanDistance(field)).toBeLessThan(BASE.radius * 1.3)
  })

  it('recruits again when the figure changes its points', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    const fewer = GRID.slice(0, 20)
    const t = runWith(field, 'speaking', 3, 0, [{ id: 'title', points: GRID, box: BOX, role: 'pointer' }])
    runWith(field, 'speaking', 3, t, [{ id: 'title', points: fewer, box: BOX, role: 'pointer' }])
    expect(recruited(field)).toHaveLength(fewer.length)
    expect(figureError(field, fewer)).toBeLessThan(12)
  })

  it('never recruits more than its share of the particles, spreading them over the points', () => {
    const field = new ParticleField({ count: 100, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    runWith(field, 'speaking', 4, 0, [{ id: 'title', points: GRID, box: BOX, role: 'lead' }])
    const ps = recruited(field)
    expect(ps.length).toBeLessThanOrEqual(FIGURE_SHARE * 100)
    expect(ps.length).toBeGreaterThan(0)
    // Spread over the whole figure: both ends of the grid are covered.
    expect(Math.min(...ps.map((p) => p.x))).toBeLessThan(BOX.x + 30)
    expect(Math.max(...ps.map((p) => p.x))).toBeGreaterThan(BOX.x + BOX.w - 30)
  })

  it('shares the particles between two figures without recruiting one twice', () => {
    const field = new ParticleField({ count: 400, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    const other = { x: 500, y: 100, w: 100, h: 50 }
    runWith(field, 'speaking', 4, 0, [
      { id: 'a', points: GRID, box: BOX, role: 'lead' },
      { id: 'b', points: GRID.slice(0, 30), box: other, role: 'pointer' },
    ])
    expect(field.particles.filter((p) => p.figure === 0)).toHaveLength(60)
    expect(field.particles.filter((p) => p.figure === 1)).toHaveLength(30)
  })

  it('gives a pointer figure its particles before a lead figure listed first shares the rest', () => {
    const field = new ParticleField({ count: 100, random: seeded(3) })
    field.resize(BASE.width, BASE.height)
    const big = Array.from({ length: 900 }, (_, i) => ({ x: (i % 30) / 29, y: Math.floor(i / 30) / 29 }))
    runWith(field, 'speaking', 4, 0, [
      { id: 'headline', points: big, box: BOX, role: 'lead' },
      { id: 'outline', points: GRID.slice(0, 40), box: { x: 500, y: 100, w: 100, h: 50 }, role: 'pointer' },
    ])
    // figure keeps the index into the frame's figures list.
    expect(field.particles.filter((p) => p.figure === 1)).toHaveLength(40)
    expect(field.particles.filter((p) => p.figure === 0)).toHaveLength(Math.floor(FIGURE_SHARE * 100) - 40)
  })

  describe('draw layers', () => {
    /** Draws at dpr 1, so each dot lands exactly on its particle. */
    function drawn(field: ParticleField, layer?: 'back' | 'front') {
      const spots: [number, number][] = []
      const ctx = {
        setTransform: () => {},
        clearRect: () => {},
        beginPath: () => {},
        fill: () => {},
        arc: (x: number, y: number) => spots.push([x, y]),
      } as unknown as CanvasRenderingContext2D
      field.draw(ctx, 1, layer)
      return spots
    }

    function staged() {
      const field = new ParticleField({ count: 100, random: seeded(7) })
      field.resize(BASE.width, BASE.height)
      runWith(field, 'speaking', 3, 0, [
        { id: 'lead', points: GRID, box: BOX, role: 'lead' },
        { id: 'pointer', points: GRID.slice(0, 20), box: { x: 500, y: 100, w: 100, h: 50 }, role: 'pointer' },
      ])
      return field
    }
    const key = (s: [number, number][]) => s.map(([x, y]) => `${x},${y}`).sort()

    it('front paints only the pointer particles and back the rest', () => {
      const field = staged()
      const pointer = field.particles.filter((p) => p.figure === 1).map((p) => `${p.x},${p.y}`).sort()
      const others = field.particles.filter((p) => p.figure !== 1).map((p) => `${p.x},${p.y}`).sort()
      expect(pointer).toHaveLength(20)
      expect(key(drawn(field, 'front'))).toEqual(pointer)
      expect(key(drawn(field, 'back'))).toEqual(others)
    })

    it('paints every particle when no layer is given', () => {
      const field = staged()
      expect(drawn(field)).toHaveLength(100)
    })
  })

  it('draws a headline bigger where few particles are recruited, and a pointer outline unchanged', () => {
    const size = (count: number, role: Figure['role']) => {
      const field = new ParticleField({ count, random: seeded(3) })
      field.resize(BASE.width, BASE.height)
      const points = Array.from({ length: 1000 }, (_, i) => ({ x: (i % 40) / 39, y: Math.floor(i / 40) / 24 }))
      runWith(field, 'speaking', 4, 0, [{ id: 'h', points, box: BOX, role }])
      const ps = recruited(field)
      return ps.reduce((sum, p) => sum + p.size, 0) / ps.length
    }
    // 1500 particles recruit 1000 points (no growth); 400 recruit 280 (the 1.5x cap).
    expect(size(400, 'lead')).toBeGreaterThan(size(1500, 'lead') * 1.3)
    expect(size(400, 'pointer')).toBeCloseTo(size(1500, 'pointer'), 0)
  })

  describe('figure depth (opt-in projection)', () => {
    const settle = (role: Figure['role'], opts: { light?: boolean; reducedMotion?: boolean; seed?: number; depth?: boolean } = {}) => {
      const field = new ParticleField({ count: 400, random: seeded(opts.seed ?? 3) })
      field.resize(BASE.width, BASE.height)
      field.setLightBackground(opts.light ?? false)
      let time = 0
      for (let i = 0; i < 4 * 60; i++) {
        time += BASE.dt
        field.step({ ...BASE, state: 'speaking', volume: 0.5, time, reducedMotion: opts.reducedMotion ?? false, figures: [{ id: 'h', points: GRID, box: BOX, role, depth: opts.depth ?? true }] })
      }
      return field
    }
    /** Mean distance from each recruited particle to its own flat (unrotated, unextruded) point. */
    const flatError = (field: ParticleField, axis: 'x' | 'both') => {
      const ps = recruited(field)
      return (
        ps.reduce((sum, p) => {
          const dx = p.x - (BOX.x + p.fx * BOX.w), dy = p.y - (BOX.y + p.fy * BOX.h)
          return sum + (axis === 'x' ? Math.abs(dx) : Math.hypot(dx, dy))
        }, 0) / ps.length
      )
    }

    it('puts about 60% of a solid figure on its front face and the rest through the thickness', () => {
      const ps = recruited(settle('lead'))
      const front = ps.filter((p) => p.fz === -1).length / ps.length
      expect(front).toBeGreaterThan(0.55)
      expect(front).toBeLessThan(0.65)
      for (const p of ps) {
        expect(p.fz).toBeGreaterThanOrEqual(-1)
        expect(p.fz).toBeLessThanOrEqual(1)
      }
      expect(ps.some((p) => p.fz > 0.5)).toBe(true)
    })

    it('settles opted-in particles on projected 3D points, off their flat points in x and scale', () => {
      const lead = settle('lead')
      // Pointer figures stay flat: only the breathing moves them off their points.
      const pointer = settle('pointer', { depth: false })
      expect(flatError(pointer, 'both')).toBeLessThan(4)
      expect(flatError(lead, 'x')).toBeGreaterThan(2.5)
      expect(flatError(lead, 'both')).toBeGreaterThan(flatError(pointer, 'both') + 1)
      expect(recruited(lead).some((p) => Math.abs(p.persp - 1) > 0.03)).toBe(true)
      for (const p of recruited(pointer)) {
        expect(p.near).toBe(1)
        expect(p.persp).toBe(1)
      }
    })

    const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
    /** The nearest and farthest thirds of a headline after it turns, by how near each dot reads. */
    const thirds = (field: ParticleField) => {
      const ps = [...recruited(field)].sort((a, b) => b.near - a.near)
      const third = Math.floor(ps.length / 3)
      return { near: ps.slice(0, third), far: ps.slice(-third) }
    }

    it('reads nearness from the turned depth, so the side turning toward the viewer is near', () => {
      // Held at a positive yaw, the right half of the front face turns toward the viewer.
      const face = recruited(settle('lead', { reducedMotion: true })).filter((p) => p.fz === -1)
      const right = face.filter((p) => p.fx > 0.6), left = face.filter((p) => p.fx < 0.4)
      expect(mean(right.map((p) => p.near))).toBeGreaterThan(mean(left.map((p) => p.near)) + 0.05)
      for (const p of recruited(settle('lead'))) {
        expect(p.near).toBeGreaterThanOrEqual(0)
        expect(p.near).toBeLessThanOrEqual(1)
      }
    })

    it('draws nearer dots larger and brighter', () => {
      const { near, far } = thirds(settle('lead'))
      expect(mean(near.map((p) => p.size))).toBeGreaterThan(mean(far.map((p) => p.size)))
      expect(mean(near.map((p) => p.alpha))).toBeGreaterThan(mean(far.map((p) => p.alpha)))
      expect(mean(near.map((p) => p.depth))).toBeGreaterThan(mean(far.map((p) => p.depth)))
    })

    it('lifts the far side on a light ground so it does not wash out', () => {
      const ratio = (light: boolean) => {
        const { near, far } = thirds(settle('lead', { light }))
        return mean(far.map((p) => p.alpha)) / mean(near.map((p) => p.alpha))
      }
      expect(ratio(true)).toBeGreaterThan(ratio(false))
    })

    it('is deterministic: the same field draws the same depths and positions', () => {
      const a = settle('lead'), b = settle('lead')
      expect(a.particles.map((p) => [p.x, p.y, p.fz, p.size])).toEqual(b.particles.map((p) => [p.x, p.y, p.fz, p.size]))
      // Depth does not come from the random source, so another seed keeps the same front share.
      const c = recruited(settle('lead', { seed: 9 }))
      expect(c.filter((p) => p.fz === -1).length / c.length).toBeCloseTo(0.6, 1)
    })

    it('holds the turn still under reduced motion, still showing depth', () => {
      const field = settle('lead', { reducedMotion: true })
      const ps = recruited(field)
      expect(flatError(field, 'x')).toBeGreaterThan(1.5)
      // A fixed turn: two frames later the targets have not moved beyond the small breathing.
      const before = ps.map((p) => [p.gx, p.gy])
      field.step({ ...BASE, state: 'speaking', volume: 0.5, time: 3.5, reducedMotion: true, figures: [{ id: 'h', points: GRID, box: BOX, role: 'lead', depth: true }] })
      ps.forEach((p, i) => {
        expect(Math.abs(p.gx - before[i][0])).toBeLessThan(3)
        expect(Math.abs(p.gy - before[i][1])).toBeLessThan(3)
      })
    })

    it('keeps a lead figure flat unless it opts in: no turn, no perspective, no extrusion', () => {
      const flat = settle('lead', { depth: false })
      expect(flatError(flat, 'both')).toBeLessThan(4)
      for (const p of recruited(flat)) {
        expect(p.near).toBe(1)
        expect(p.persp).toBe(1)
      }
      // Reduced motion changes nothing for a flat figure: there is no still yaw.
      expect(flatError(settle('lead', { depth: false, reducedMotion: true }), 'both')).toBeLessThan(4)
      // The same figure that opts in is off its flat points.
      expect(flatError(settle('lead', { depth: true }), 'both')).toBeGreaterThan(flatError(flat, 'both') + 1)
    })
  })

  it('keeps every position finite with figures, also under reduced motion and while idle', () => {
    const field = new ParticleField({ count: 200, random: seeded(5) })
    field.resize(BASE.width, BASE.height)
    let time = 0
    for (let i = 0; i < 120; i++) {
      time += BASE.dt
      field.step({ ...BASE, state: 'idle', volume: 0, time, reducedMotion: true, figures: [{ id: 'x', points: GRID, box: BOX, role: 'lead' }] })
    }
    for (const p of field.particles) {
      expect(Number.isFinite(p.x)).toBe(true)
      expect(Number.isFinite(p.y)).toBe(true)
    }
    expect(figureError(field, GRID)).toBeLessThan(12)
  })
})
