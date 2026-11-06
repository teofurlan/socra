/**
 * Particle field behind the exam screen: particles drift loose over the whole screen while
 * nothing is said, and gather around the visualizer's slot, into a rotating sphere or a sound
 * wave, whenever there is a voice (speaking, listening) or the examiner is thinking. A screen
 * with nothing to say yet (the agent setup) can ask them to rest there, small and slow.
 *
 * Plain TypeScript with no React, so the physics can be tested without a canvas.
 */
import { applyMatrix, idleTurn, isSide, solidMatrix, type Mat3, type SolidPose } from '@/lib/solidShapes'

export type FieldState = 'idle' | 'speaking' | 'listening' | 'thinking'
export type FieldShape = 'sphere' | 'wave'

export interface FieldFrame {
  /** Seconds since the previous frame. */
  dt: number
  /** Seconds, monotonic. */
  time: number
  width: number
  height: number
  /** Centre and radius of the visualizer's slot, in the same pixels as width/height. */
  cx: number
  cy: number
  radius: number
  state: FieldState
  /** Raw voice level 0..1; the field smooths it. */
  volume: number
  reducedMotion: boolean
  /** While idle, gather into a small, slow formation instead of drifting loose. */
  rest?: boolean
  /** Shapes the particles assemble on screen while they are shown; omitted or empty for none. */
  figures?: Figure[]
}

/**
 * A point of a figure, normalised to 0..1 of its box; ``a`` is the stroke angle there, unused by
 * the dot look. A point of a solid also has its depth ``z`` (in half boxes, away from the viewer
 * is positive) and its unit surface normal ``nx, ny, nz``.
 */
export interface FigurePoint {
  x: number
  y: number
  a?: number
  z?: number
  nx?: number
  ny?: number
  nz?: number
}

export interface FigureBox {
  x: number
  y: number
  w: number
  h: number
}

/**
 * Something the particles assemble: a share of them is recruited, one per point, and the
 * rest carry on. A ``lead`` figure takes the stage, so the rest drift loose instead of
 * forming the voice shape; a ``pointer`` figure only borrows a few, leaving the voice shape.
 * A figure keeps its particles while its ``id`` and ``points`` stay the same; its box is read
 * every frame, so it follows whatever it is drawn on.
 */
export interface Figure {
  id: string
  points: FigurePoint[]
  box: FigureBox
  role: 'lead' | 'pointer'
  /**
   * Opt-in 3D for solid figures (spheres, cylinders, ...): points get a depth through a
   * thickness, the figure turns slowly and is drawn in perspective, nearer dots larger and
   * brighter. Off by default: headlines and outlines are flat 2D, so text stays easy to read.
   */
  depth?: boolean
  /**
   * Makes the figure a solid body (with ``depth``): its points carry their own depth and normal
   * and turn by this pose, in turns, from the scene's state, plus a slow idle turn that holds
   * still under reduced motion. Points whose turned normal faces the viewer take the first
   * colour of the palette, the sides the second (``isSide``). The pose is the only state: the
   * same pose gives the same picture.
   */
  pose?: SolidPose
}

/** At most this share of the particles is recruited by figures, all together. */
export const FIGURE_SHARE = 0.7

export interface Particle {
  x: number
  y: number
  vx: number
  vy: number
  /** Loose position, normalised to 0..1 of the screen. */
  hx: number
  hy: number
  /** How far this particle has gathered, 0..1. */
  g: number
  /** Unit-sphere direction it takes in the formation. */
  dx: number
  dy: number
  dz: number
  /** Sound-wave strand it belongs to, its place along it (-1..1) and across it (about -1..1). */
  strand: number
  u: number
  v: number
  hue: number
  rate: number
  ph: number
  spd: number
  // Render attributes, refreshed by step().
  depth: number
  alpha: number
  size: number
  /** Where in the two-colour gradient it is painted, 0..1. */
  tint: number
  /** Index of the figure it is recruited by in the current frame's figures, or -1. */
  figure: number
  /** How far it has moved onto its figure, 0..1, and its point there (0..1 of the box). */
  fg: number
  fx: number
  fy: number
  /**
   * Depth through a depth figure's thickness, -1 (front face) .. 1 (back), fixed per recruit; and
   * how near it reads this frame (0 back .. 1 front) with the perspective scale it is drawn at.
   */
  fz: number
  /** Of a solid figure's point: depth in half boxes and surface normal. */
  fpz: number
  fnx: number
  fny: number
  fnz: number
  /** Side colour of a solid's point, 0 front (first colour) .. 1 side (second), eased as it turns. */
  st: number
  near: number
  persp: number
  /** Whether its current figure is a pointer, so it is painted over the content; set by step(). */
  pointer: boolean
  /** Last screen point of its figure, where it lets go from once the figure is gone. */
  gx: number
  gy: number
}

const TAU = Math.PI * 2
const TILT = 0.38
/** Five sine strands that cross one another; each pinches to a point at both ends. */
const STRANDS = [
  { amp: 1.0, f: 1.35, s: 2.3, ph: 0.0, thick: 1.0, alpha: 1.0, hue: 0.0 },
  { amp: 0.78, f: 2.05, s: -1.9, ph: 1.7, thick: 0.85, alpha: 0.85, hue: 1.0 },
  { amp: 0.6, f: 2.9, s: 3.0, ph: 3.1, thick: 0.7, alpha: 0.72, hue: 0.35 },
  { amp: 0.46, f: 1.75, s: -2.6, ph: 4.4, thick: 0.6, alpha: 0.6, hue: 0.7 },
  { amp: 0.32, f: 3.6, s: 1.6, ph: 5.2, thick: 0.5, alpha: 0.5, hue: 0.5 },
]
/** The loose flow wraps over this span (-0.04..1.04 of the screen); the flow field repeats with it. */
const FLOW = (TAU / 1.08)
const BUCKETS = 10
/** Figure depth (``Figure.depth``): the share of its particles on the front face, and the thickness as a share of the box height. */
const FRONT_SHARE = 0.6
const THICKNESS = 0.22
/** The figure turns slowly so the depth reads: yaw and pitch amplitudes (rad) and speeds, and the perspective focal length as a share of the box width. */
const YAW = 0.28
const PITCH = 0.12
const FOCAL = 1.4
/** Under reduced motion the turn holds still at this small yaw, so the depth still reads. */
const STILL_YAW = 0.16
const GOLDEN = 0.6180339887498949
/** A solid's point whose surface turns fully away from the viewer keeps this share of its brightness. */
const BACK_DIM = 0.45
/**
 * Headline dot size follows density. Letters read filled when the dots are about one spacing
 * wide, and spacing shrinks with the square root of the dot count, so a headline holding fewer
 * than HEADLINE_FULL particles draws its dots sqrt(HEADLINE_FULL / count) times larger, at most
 * HEADLINE_FILL_MAX. 1000 is about what a 1440x900 screen recruits (1007), so desktop keeps
 * the normal size; a 360x640 phone recruits 280 and gets the 1.5x cap.
 */
const HEADLINE_FULL = 1000
const HEADLINE_FILL_MAX = 1.5
export function headlineDotScale(recruited: number): number {
  return recruited <= 0 ? 1 : clamp(Math.sqrt(HEADLINE_FULL / recruited), 1, HEADLINE_FILL_MAX)
}

const clamp = (v: number, a: number, b: number) => (v < a ? a : v > b ? b : v)
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const smooth = (t: number) => t * t * (3 - 2 * t)

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.replace('#', ''), 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}

/** Points spread evenly over the unit sphere (golden-angle spiral). */
export function fibonacciSphere(n: number): { x: number; y: number; z: number }[] {
  const golden = Math.PI * (3 - Math.sqrt(5))
  return Array.from({ length: n }, (_, i) => {
    const y = 1 - (2 * (i + 0.5)) / n
    const r = Math.sqrt(1 - y * y)
    return { x: Math.cos(i * golden) * r, y, z: Math.sin(i * golden) * r }
  })
}

/** Enough particles to fill the screen without drowning it, scaled by area. */
export function particleCount(width: number, height: number): number {
  return Math.round(clamp((width * height) / 900, 400, 1800))
}

/** A speech-like level for when no real audio level is available. */
export function simulatedVoice(t: number): number {
  const phrase = clamp((Math.sin(t * 1.1) + Math.sin(t * 0.37 + 1) + 0.4) * 2, 0, 1)
  const syllable = Math.pow(Math.abs(Math.sin(t * 5 * Math.PI + Math.sin(t * 1.7) * 1.2)), 1.4)
  return phrase * (0.22 + 0.78 * syllable)
}

export interface ParticleFieldOptions {
  count: number
  shape?: FieldShape
  random?: () => number
}

export class ParticleField {
  particles: Particle[] = []
  shape: FieldShape
  private random: () => number
  private width = 1
  private height = 1
  private level = 0
  private rot = 0
  private col0: [number, number, number] = [129, 140, 248]
  private col1: [number, number, number] = [192, 132, 252]
  private target0 = this.col0
  private target1 = this.col1
  /** Particle indices in a fixed random order, so figures recruit from all over the screen. */
  private order: number[] = []
  /** Who each figure recruited, kept while its id and points stay the same. */
  private recruits: { id: string; points: FigurePoint[]; members: number[] }[] = []
  /** Additive light reads on a dark ground; a light ground needs plain paint. */
  private additive = 'lighter' as GlobalCompositeOperation

  constructor({ count, shape = 'sphere', random = Math.random }: ParticleFieldOptions) {
    this.shape = shape
    this.random = random
    this.setCount(count)
  }

  private sized = false

  resize(width: number, height: number) {
    this.width = width
    this.height = height
    // Particles are built before the screen size is known: put them at their homes once.
    if (!this.sized) {
      this.sized = true
      for (const p of this.particles) {
        p.x = p.hx * width
        p.y = p.hy * height
      }
    }
  }

  /** Rebuilds the formation for a new count, keeping existing particles where they are. */
  setCount(count: number) {
    const rnd = this.random
    const sphere = fibonacciSphere(count)
    const perStrand = Math.ceil(count / STRANDS.length)
    this.particles = sphere.map((d, i) => {
      const old = this.particles[i]
      const hx = old ? old.hx : rnd()
      const hy = old ? old.hy : rnd()
      const hue = rnd()
      return {
        x: old ? old.x : hx * this.width,
        y: old ? old.y : hy * this.height,
        vx: 0,
        vy: 0,
        hx,
        hy,
        g: old ? old.g : 0,
        dx: d.x,
        dy: d.y,
        dz: d.z,
        strand: i % STRANDS.length,
        u: -1 + 2 * ((Math.floor(i / STRANDS.length) + rnd()) / perStrand),
        v: (rnd() + rnd() + rnd()) / 1.5 - 1,
        hue,
        rate: 0.8 + rnd() * 2.6,
        ph: rnd() * TAU,
        spd: 0.4 + rnd() * 0.6,
        depth: 0.5,
        alpha: 0,
        size: 1,
        tint: hue,
        figure: -1,
        fg: 0,
        fx: 0,
        fy: 0,
        fz: -1,
        fpz: 0,
        fnx: 0,
        fny: 0,
        fnz: 0,
        st: 0,
        near: 1,
        persp: 1,
        pointer: false,
        gx: 0,
        gy: 0,
      }
    })
    this.order = this.particles.map((_, i) => i)
    for (let i = this.order.length - 1; i > 0; i--) {
      const j = Math.floor(rnd() * (i + 1))
      ;[this.order[i], this.order[j]] = [this.order[j], this.order[i]]
    }
    this.recruits = []
  }

  /**
   * Matches recruits to this frame's figures: a figure with the same id and points keeps its
   * particles, a new or changed one recruits free particles, one per point (spread evenly over
   * its points when the share runs short), and particles of figures that went away are freed.
   */
  private recruit(figures: Figure[]) {
    const same =
      figures.length === this.recruits.length &&
      figures.every((f, i) => f.id === this.recruits[i].id && f.points === this.recruits[i].points)
    if (same) return

    const previous = new Map(this.recruits.map((r) => [r.id, r]))
    const kept = new Map<string, number[]>()
    const taken = new Set<number>()
    for (const f of figures) {
      const r = previous.get(f.id)
      if (r && r.points === f.points && !kept.has(f.id)) {
        kept.set(f.id, r.members)
        r.members.forEach((i) => taken.add(i))
      }
    }

    let budget = Math.floor(FIGURE_SHARE * this.particles.length) - taken.size
    let cursor = 0
    const membersOf: (number[] | undefined)[] = figures.map((f) => kept.get(f.id))
    const firstOf = new Map<string, number>()
    figures.forEach((f, n) => firstOf.has(f.id) || firstOf.set(f.id, n))
    // Pointers recruit before leads, so a big headline cannot leave the focus outline empty;
    // every figure keeps its index in the frame's list.
    const turns = figures.map((_, n) => n).sort((a, b) => Number(figures[a].role !== 'pointer') - Number(figures[b].role !== 'pointer'))
    for (const n of turns) {
      const f = figures[n]
      let members = firstOf.get(f.id) === n ? membersOf[n] : undefined
      if (!members) {
        const want = Math.max(0, Math.min(f.points.length, budget))
        budget -= want
        members = []
        while (members.length < want && cursor < this.order.length) {
          const i = this.order[cursor++]
          if (!taken.has(i)) {
            taken.add(i)
            members.push(i)
          }
        }
        members.forEach((i, k) => {
          const q = f.points[Math.floor((k * f.points.length) / members!.length)]
          const p = this.particles[i]
          p.fx = q.x
          p.fy = q.y
          p.fpz = q.z ?? 0
          p.fnx = q.nx ?? 0
          p.fny = q.ny ?? 0
          p.fnz = q.nz ?? 0
          // Depth through a solid figure: golden-ratio spacing by rank, so the share on the front
          // face is the same for any figure and every run.
          const u = ((k + 0.5) * GOLDEN) % 1
          p.fz = u < FRONT_SHARE ? -1 : -1 + (2 * (u - FRONT_SHARE)) / (1 - FRONT_SHARE)
        })
      }
      membersOf[n] = members
    }
    const next: typeof this.recruits = figures.map((f, n) => ({ id: f.id, points: f.points, members: membersOf[n] ?? [] }))

    for (const p of this.particles) p.figure = -1
    next.forEach((r, n) => r.members.forEach((i) => (this.particles[i].figure = n)))
    this.recruits = next
  }

  /** The particles keep their places and glide into the new formation. */
  setShape(shape: FieldShape) {
    this.shape = shape
  }

  setLightBackground(light: boolean) {
    this.additive = light ? 'source-over' : 'lighter'
  }

  /** Dimmer at rest; less so on a light ground, where overlapping paint does not add up. */
  private restAlpha() {
    return this.additive === 'lighter' ? 0.55 : 0.85
  }

  setColors(colors: [string, string]) {
    this.target0 = hexToRgb(colors[0])
    this.target1 = hexToRgb(colors[1])
  }

  step(f: FieldFrame) {
    const { dt, time: t, width: W, height: H, cx, cy } = f
    this.width = W
    this.height = H
    const motion = f.reducedMotion ? 0.4 : 1

    this.level += (f.volume - this.level) * (1 - Math.exp(-dt * (f.volume > this.level ? 26 : 8)))
    const vol = this.level
    // At rest the formation is smaller and turns and flows at a fraction of its speed.
    const resting = f.state === 'idle' && f.rest === true
    const calm = resting ? 0.4 : 1
    this.rot += dt * (f.state === 'thinking' ? 0.9 : 0.22 + vol * 0.7) * motion * calm

    const ck = 1 - Math.exp(-dt * 3)
    for (let i = 0; i < 3; i++) {
      this.col0[i] = lerp(this.col0[i], this.target0[i], ck)
      this.col1[i] = lerp(this.col1[i], this.target1[i], ck)
    }

    const figures = f.figures ?? []
    this.recruit(figures)
    const lead = figures.some((fig) => fig.role === 'lead')
    // A lead figure takes the stage: everyone else drifts loose as if nothing were said.
    const G = (f.state === 'idle' && !resting) || lead ? 0 : 1
    const R = f.radius * (resting ? 0.6 : 0.85) * (1 + vol * 0.1)
    // A solid's turn is the same for all its points: the scene's pose plus the idle angle.
    const turns: (Mat3 | null)[] = figures.map((fig) => (fig.depth && fig.pose ? solidMatrix(fig.pose, idleTurn(t, f.reducedMotion)) : null))
    const cr = Math.cos(this.rot), sr = Math.sin(this.rot)
    const ct = Math.cos(TILT), st = Math.sin(TILT)
    const wave = this.shape === 'wave'
    const halfW = Math.min(f.radius * (resting ? 1.7 : 2.4), W * 0.45)

    for (const p of this.particles) {
      // Loose home: a slow flow field over the whole screen, wrapping at the edges.
      // The flow repeats over the wrap (period WRAP), so a particle leaving one edge meets the same
      // direction coming in at the other and is not wrapped back at once, frame after frame.
      const da = p.ph + Math.sin(t * 0.11 + p.hy * FLOW) * 1.6 + Math.cos(t * 0.07 + p.hx * FLOW)
      p.hx += Math.cos(da) * 0.006 * dt * p.spd * motion * (H / W)
      p.hy += Math.sin(da) * 0.006 * dt * p.spd * motion
      let wx = 0, wy = 0
      if (p.hx < -0.04) { p.hx += 1.08; wx = 1.08 } else if (p.hx > 1.04) { p.hx -= 1.08; wx = -1.08 }
      if (p.hy < -0.04) { p.hy += 1.08; wy = 1.08 } else if (p.hy > 1.04) { p.hy -= 1.08; wy = -1.08 }

      p.g += (G - p.g) * (1 - Math.exp(-dt * p.rate))
      const e = smooth(clamp(p.g, 0, 1))
      // The loose home is only part of the target while a particle is loose: weighted by what is
      // left of it once the formation and then the figure have taken their share (see tx below).
      // Moving the particle by more than that flings a recruit, which then flies back to its figure.
      if (wx || wy) {
        const loose = (1 - e) * (1 - smooth(clamp(p.fg, 0, 1)))
        p.x += wx * W * loose
        p.y += wy * H * loose
      }

      let fx: number, fy: number, depth: number
      if (wave) {
        // Formation: a thick strand of a sound wave whose height follows the voice. It keeps a
        // calm resting swell, so the strands never collapse into one line between words.
        const c = STRANDS[p.strand]
        const A = R * 0.65 * (0.3 + 0.7 * vol) * c.amp
        const base = Math.max(0, 1 - p.u * p.u)
        const env = Math.pow(base, 1.6)
        const arg = p.u * c.f * Math.PI + t * c.s * motion * calm + c.ph
        const sn = Math.sin(arg)
        const thick = R * (0.05 + 0.15 * vol * c.thick) * (0.35 + 0.65 * env)
        fx = cx + p.u * halfW
        fy = cy + sn * A * env + p.v * thick
        depth = c.alpha
      } else {
        // Formation: a rotating, tilted sphere whose surface ripples with the voice.
        const n = Math.sin(p.dx * 3.1 + t * 1.9) * Math.sin(p.dy * 3.7 - t * 1.4) * Math.sin(p.dz * 2.9 + t * 1.1)
        const d = 1 + vol * 0.34 * n + 0.025 * Math.sin(t * 1.2)
        const x = p.dx * d, y = p.dy * d, z = p.dz * d
        const x1 = x * cr + z * sr, z1 = -x * sr + z * cr
        const y2 = y * ct - z1 * st, z2 = y * st + z1 * ct
        const s = 1 / (1 - z2 * 0.28)
        fx = cx + x1 * R * s
        fy = cy + y2 * R * s
        depth = clamp((z2 + 1) / 2, 0, 1)
      }

      // A recruited particle moves onto its figure point, which breathes with the voice.
      const fig = p.figure >= 0 ? figures[p.figure] : undefined
      // Stays on its layer while it flies back after the figure is gone, so it never jumps layers mid-flight.
      if (fig) p.pointer = fig.role === 'pointer'
      else if (p.fg === 0) p.pointer = false
      p.fg += ((fig ? 1 : 0) - p.fg) * (1 - Math.exp(-dt * (p.rate + 1.5)))
      if (p.fg < 1e-3) p.fg = 0
      const ef = smooth(clamp(p.fg, 0, 1))
      let gx = 0, gy = 0
      // Set for a solid's point: where in the two colours it sits, 0 front .. 1 side.
      let sideTint = -1
      // Set for a solid's point: 1 facing the viewer .. BACK_DIM when its surface turns away, so the
      // near surface hides the far one and the silhouette reads.
      let facing = 1
      if (fig) {
        const breath = (1.2 + 2.6 * vol) * motion
        let ox = (p.fx - 0.5) * fig.box.w, oy = (p.fy - 0.5) * fig.box.h
        if (fig.depth) {
          // A depth figure is projected from 3D: a flat figure is a slab, its points at their depth
          // through a thickness and the whole figure turning a little; a solid's points have their
          // own depth and turn by the scene's pose. Both share the perspective and the nearness.
          const turn = turns[p.figure]
          let x1: number, y2: number, z2: number, reach: number
          if (turn) {
            ;[x1, y2, z2] = applyMatrix(turn, ox, oy, p.fpz * fig.box.w * 0.5)
            reach = fig.box.w / 2
            const nz = applyMatrix(turn, p.fnx, p.fny, p.fnz)[2]
            const side = isSide(nz) ? 1 : 0
            facing = lerp(1, BACK_DIM, clamp(nz / 0.5, 0, 1))
            p.st = p.fg < 0.05 ? side : p.st + (side - p.st) * (1 - Math.exp(-dt * 10))
            sideTint = p.st
          } else {
            const yaw = f.reducedMotion ? STILL_YAW : YAW * Math.sin(t * 0.55)
            const pitch = f.reducedMotion ? 0 : PITCH * Math.sin(t * 0.37 + 1)
            const oz = p.fz * THICKNESS * fig.box.h
            const cyw = Math.cos(yaw), syw = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch)
            x1 = ox * cyw + oz * syw
            const z1 = -ox * syw + oz * cyw
            y2 = oy * cp - z1 * sp
            z2 = oy * sp + z1 * cp
            reach = Math.hypot(fig.box.w / 2, THICKNESS * fig.box.h)
          }
          const focal = FOCAL * fig.box.w
          p.persp = focal / Math.max(focal * 0.2, focal + z2)
          // Nearness follows the turned depth, scaled by the farthest a point can reach, so the
          // side turning toward the viewer grows and brightens without saturating.
          p.near = clamp(0.5 - z2 / (2 * reach), 0, 1)
          ox = x1 * p.persp
          oy = y2 * p.persp
        } else {
          p.persp = 1
          p.near = 1
        }
        gx = fig.box.x + fig.box.w / 2 + ox + Math.sin(t * 2.3 + p.ph) * breath
        gy = fig.box.y + fig.box.h / 2 + oy + Math.cos(t * 1.9 + p.ph * 1.3) * breath
        p.gx = gx
        p.gy = gy
      } else if (p.fg > 0) {
        gx = p.gx
        gy = p.gy
      }

      // Spring toward a blend of the loose home and the formation, swirling while in transit.
      const tx = lerp(lerp(p.hx * W, fx, e), gx, ef), ty = lerp(lerp(p.hy * H, fy, e), gy, ef)
      const k = lerp(lerp(9, 95, e), 110, ef), c = 2 * Math.sqrt(k) * 0.78
      let ax = (tx - p.x) * k - p.vx * c
      let ay = (ty - p.y) * k - p.vy * c
      const transit = e * (1 - e) * 4 * (f.reducedMotion ? 0.3 : 1) * (1 - ef)
      if (transit > 0.01) {
        const rx = p.x - cx, ry = p.y - cy, rl = Math.hypot(rx, ry) + 1
        ax += (-ry / rl) * 700 * transit
        ay += (rx / rl) * 700 * transit
      }
      p.vx += ax * dt
      p.vy += ay * dt
      p.x += p.vx * dt
      p.y += p.vy * dt

      const speed = Math.hypot(p.vx, p.vy), w = clamp(speed / 140, 0, 1)

      const twinkle = 0.7 + 0.3 * Math.sin(t * (0.8 + p.spd) + p.ph)
      p.depth = lerp(0.5, depth, e)
      p.alpha = lerp(0.16 * twinkle, wave ? 0.35 + 0.65 * depth : 0.22 + 0.78 * depth, e) * (resting ? this.restAlpha() : 1)
      const scale = wave ? 0.85 + 0.25 * depth : 0.75 + 0.55 * depth
      p.size = lerp(7, 4 + 10 * vol + 3 * depth, e) * lerp(1, scale, e) + w * 6 * (1 - e)
      // On the wave each strand leans toward its own colour; at rest everything leans to the first.
      p.tint = wave ? lerp(p.hue, STRANDS[p.strand].hue, 0.75 * e) : p.hue
      if (resting) p.tint *= 0.3
      if (ef > 0) {
        // A figure is drawn bright and even, so it reads as one shape; it swells with the voice.
        // A depth figure's nearer dots are larger and brighter; the far side keeps a higher floor
        // on a light ground, where it would wash out. A flat headline's dots grow where few
        // particles are recruited (headlineDotScale).
        const fill = fig && fig.role === 'lead' ? headlineDotScale(this.recruits[p.figure]?.members.length ?? 0) : 1
        const far = this.additive === 'lighter' ? 0.4 : 0.7
        p.depth = lerp(p.depth, p.near, ef)
        p.alpha = lerp(p.alpha, (0.62 + 0.3 * twinkle * (0.5 + vol)) * (far + (1 - far) * p.near) * facing, ef)
        p.size = lerp(p.size, (5 + 5 * vol) * (0.6 + 0.9 * p.near) * p.persp * fill, ef)
        if (sideTint >= 0) p.tint = lerp(p.tint, sideTint, ef)
      }
    }
  }

  /**
   * Paints the particles. With a ``layer`` only that one is painted: ``front`` is the particles
   * a pointer figure recruited (drawn over the content), ``back`` all the others. Without one,
   * everything is painted.
   */
  draw(ctx: CanvasRenderingContext2D, dpr: number, layer?: 'back' | 'front') {
    const shown = (p: Particle) => layer === undefined || p.pointer === (layer === 'front')
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'
    ctx.clearRect(0, 0, this.width, this.height)

    const colors: string[] = []
    for (let b = 0; b < BUCKETS; b++) {
      const m = b / (BUCKETS - 1)
      const [a, c] = [this.col0, this.col1]
      colors.push(`rgb(${lerp(a[0], c[0], m) | 0},${lerp(a[1], c[1], m) | 0},${lerp(a[2], c[2], m) | 0})`)
    }

    // Round dots, nearer and brighter ones larger; light adds up on a dark ground only.
    ctx.globalCompositeOperation = this.additive
    for (const p of this.particles) {
      if (!shown(p)) continue
      ctx.globalAlpha = p.alpha
      ctx.fillStyle = colors[Math.min(BUCKETS - 1, (p.tint * BUCKETS) | 0)]
      ctx.beginPath()
      ctx.arc(p.x, p.y, 0.6 + p.size * 0.16, 0, TAU)
      ctx.fill()
    }
    ctx.globalAlpha = 1
    ctx.globalCompositeOperation = 'source-over'
  }
}
