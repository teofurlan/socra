/**
 * 3D solids for the particle field: points sampled on a cube, cylinder, cone, sphere or torus
 * (on the surface, or along the edges for a wireframe), and the turn that shows them.
 *
 * Plain TypeScript, no randomness and no DOM: the same kind and count always give the same
 * points, so the pose of a shape depends only on the scene state and the clock.
 *
 * Space: every point lies inside the unit sphere (x right, y DOWN as on screen, z away from the
 * viewer), so a box of any size can hold the solid whatever its pose. ``nx, ny, nz`` is the
 * unit outward normal of the surface (or, on an edge, of the two faces that meet there).
 */

export type SolidKind = 'cube' | 'cylinder' | 'cone' | 'sphere' | 'torus'

export const SOLID_KINDS: readonly SolidKind[] = ['cube', 'cylinder', 'cone', 'sphere', 'torus']

export interface SolidPoint {
  x: number
  y: number
  z: number
  nx: number
  ny: number
  nz: number
}

/** The scene's rotation state of a shape, in turns (0.25 is a quarter turn), as ``rotate`` sets it. */
export interface SolidPose {
  rx: number
  ry: number
  rz: number
}

/** A row-major 3x3 rotation matrix. */
export type Mat3 = readonly [number, number, number, number, number, number, number, number, number]

const TAU = Math.PI * 2
const HALF = 0.57 // cube half side: its corner is 0.99 from the centre
const CYL_R = 0.6
const CYL_H = 0.6 // half height
const CONE_R = 0.6
const CONE_H = 0.6 // half height; the apex is up (negative y), the base down
const SPHERE_R = 0.85
const TORUS_R = 0.62 // from the centre to the middle of the tube
const TORUS_T = 0.26 // tube radius

interface Region {
  /** Share of the points: surface area or edge length. */
  weight: number
  /** The ``j``-th of ``n`` points of this region. */
  at: (j: number, n: number) => SolidPoint
}

function point(x: number, y: number, z: number, nx: number, ny: number, nz: number): SolidPoint {
  const length = Math.hypot(nx, ny, nz) || 1
  return { x, y, z, nx: nx / length, ny: ny / length, nz: nz / length }
}

/** Low-discrepancy pair in 0..1 (R2 sequence): any prefix covers a patch evenly, with no randomness. */
function r2(j: number): [number, number] {
  return [(0.5 + j * 0.7548776662466927) % 1, (0.5 + j * 0.5698402909980532) % 1]
}

/** ``count`` split in proportion to the weights, exactly, by largest remainder (ties to the first). */
function allocate(count: number, weights: number[]): number[] {
  const total = weights.reduce((a, b) => a + b, 0)
  const exact = weights.map((w) => (count * w) / total)
  const counts = exact.map(Math.floor)
  let left = count - counts.reduce((a, b) => a + b, 0)
  const order = exact.map((_, i) => i).sort((a, b) => exact[b] - Math.floor(exact[b]) - (exact[a] - Math.floor(exact[a])) || a - b)
  for (const i of order) {
    if (left-- <= 0) break
    counts[i]++
  }
  return counts
}

function unit(axis: number): [number, number, number] {
  return [axis === 0 ? 1 : 0, axis === 1 ? 1 : 0, axis === 2 ? 1 : 0]
}

/** Position along a line from ``a`` to ``b``, evenly spaced. */
function along(a: number[], b: number[], t: number): [number, number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t]
}

/** The tube angle whose share of a torus's surface area (which grows with the radius) is ``w``. */
function tubeAngle(w: number): number {
  // Area up to angle v is proportional to R*v + r*sin(v); R > r keeps it increasing, so bisect.
  const target = w * TAU * TORUS_R
  let lo = 0
  let hi = TAU
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2
    if (TORUS_R * mid + TORUS_T * Math.sin(mid) < target) lo = mid
    else hi = mid
  }
  return (lo + hi) / 2
}

/** A circle of ``radius`` around the y axis at height ``y``; ``tilt`` leans its normal up or down. */
function ring(radius: number, y: number, tilt: number): Region {
  return {
    weight: TAU * radius,
    at: (j, n) => {
      const a = TAU * ((j + 0.5) / n)
      return point(radius * Math.cos(a), y, radius * Math.sin(a), Math.cos(a), tilt, Math.sin(a))
    },
  }
}

/** A circle in the plane perpendicular to ``axis``, centred at the origin (great circle of the sphere). */
function great(axis: number): Region {
  const [i, j] = [0, 1, 2].filter((k) => k !== axis)
  return {
    weight: TAU * SPHERE_R,
    at: (k, n) => {
      const a = TAU * ((k + 0.5) / n)
      const p = [0, 0, 0]
      p[i] = SPHERE_R * Math.cos(a)
      p[j] = SPHERE_R * Math.sin(a)
      return point(p[0], p[1], p[2], p[0], p[1], p[2])
    },
  }
}

function surfaceRegions(kind: SolidKind): Region[] {
  switch (kind) {
    case 'cube': {
      const faces: Region[] = []
      for (let axis = 0; axis < 3; axis++) {
        for (const sign of [-1, 1]) {
          const [i, j] = [0, 1, 2].filter((k) => k !== axis)
          faces.push({
            weight: (2 * HALF) ** 2,
            at: (k) => {
              const [u, v] = r2(k) // the sequence restarts on every face
              const p = [0, 0, 0]
              p[axis] = sign * HALF
              p[i] = (2 * u - 1) * HALF
              p[j] = (2 * v - 1) * HALF
              const [nx, ny, nz] = unit(axis)
              return point(p[0], p[1], p[2], nx * sign, ny * sign, nz * sign)
            },
          })
        }
      }
      return faces
    }
    case 'cylinder':
      return [
        {
          weight: TAU * CYL_R * 2 * CYL_H,
          at: (k) => {
            const [u, v] = r2(k)
            const a = TAU * u
            return point(CYL_R * Math.cos(a), (2 * v - 1) * CYL_H, CYL_R * Math.sin(a), Math.cos(a), 0, Math.sin(a))
          },
        },
        ...[-1, 1].map((sign): Region => ({
          weight: Math.PI * CYL_R * CYL_R,
          at: (k) => {
            const [u, v] = r2(k)
            const a = TAU * u
            const r = CYL_R * Math.sqrt(v)
            return point(r * Math.cos(a), sign * CYL_H, r * Math.sin(a), 0, sign, 0)
          },
        })),
      ]
    case 'cone': {
      const slant = Math.hypot(CONE_R, 2 * CONE_H)
      return [
        {
          weight: Math.PI * CONE_R * slant,
          at: (k) => {
            const [u, v] = r2(k)
            const a = TAU * u
            const rho = Math.sqrt(v) // distance from the apex as a share of the slant; area grows with its square
            const r = CONE_R * rho
            return point(r * Math.cos(a), -CONE_H + 2 * CONE_H * rho, r * Math.sin(a), (2 * CONE_H * Math.cos(a)) / slant, -CONE_R / slant, (2 * CONE_H * Math.sin(a)) / slant)
          },
        },
        {
          weight: Math.PI * CONE_R * CONE_R,
          at: (k) => {
            const [u, v] = r2(k)
            const a = TAU * u
            const r = CONE_R * Math.sqrt(v)
            return point(r * Math.cos(a), CONE_H, r * Math.sin(a), 0, 1, 0)
          },
        },
      ]
    }
    case 'sphere':
      return [
        {
          weight: 1,
          at: (k, n) => {
            const y = 1 - (2 * (k + 0.5)) / n
            const r = Math.sqrt(1 - y * y)
            const a = k * Math.PI * (3 - Math.sqrt(5))
            const [x, z] = [Math.cos(a) * r, Math.sin(a) * r]
            return point(SPHERE_R * x, SPHERE_R * y, SPHERE_R * z, x, y, z)
          },
        },
      ]
    case 'torus':
      return [
        {
          weight: 1,
          at: (k) => {
            const [u, w] = r2(k)
            const a = TAU * u
            const v = tubeAngle(w)
            const radius = TORUS_R + TORUS_T * Math.cos(v)
            return point(radius * Math.cos(a), TORUS_T * Math.sin(v), radius * Math.sin(a), Math.cos(v) * Math.cos(a), Math.sin(v), Math.cos(v) * Math.sin(a))
          },
        },
      ]
  }
}

function edgeRegions(kind: SolidKind): Region[] {
  switch (kind) {
    case 'cube': {
      const edges: Region[] = []
      for (let axis = 0; axis < 3; axis++) {
        const [i, j] = [0, 1, 2].filter((k) => k !== axis)
        for (const si of [-1, 1]) {
          for (const sj of [-1, 1]) {
            edges.push({
              weight: 2 * HALF,
              at: (k, n) => {
                const p = [0, 0, 0]
                p[axis] = (2 * ((k + 0.5) / n) - 1) * HALF
                p[i] = si * HALF
                p[j] = sj * HALF
                const normal = [0, 0, 0]
                normal[i] = si
                normal[j] = sj
                return point(p[0], p[1], p[2], normal[0], normal[1], normal[2])
              },
            })
          }
        }
      }
      return edges
    }
    case 'cylinder': {
      const posts = [0, 1, 2, 3].map((q): Region => ({
        weight: 2 * CYL_H,
        at: (k, n) => {
          const a = (q * TAU) / 4
          const y = (2 * ((k + 0.5) / n) - 1) * CYL_H
          return point(CYL_R * Math.cos(a), y, CYL_R * Math.sin(a), Math.cos(a), 0, Math.sin(a))
        },
      }))
      return [ring(CYL_R, -CYL_H, -1), ring(CYL_R, CYL_H, 1), ...posts]
    }
    case 'cone': {
      const slant = Math.hypot(CONE_R, 2 * CONE_H)
      const lines = [0, 1, 2, 3].map((q): Region => ({
        weight: slant,
        at: (k, n) => {
          const a = (q * TAU) / 4 + Math.PI / 4
          const p = along([0, -CONE_H, 0], [CONE_R * Math.cos(a), CONE_H, CONE_R * Math.sin(a)], (k + 0.5) / n)
          return point(p[0], p[1], p[2], (2 * CONE_H * Math.cos(a)) / slant, -CONE_R / slant, (2 * CONE_H * Math.sin(a)) / slant)
        },
      }))
      return [ring(CONE_R, CONE_H, 1), ...lines]
    }
    case 'sphere': {
      const parallel = (y: number): Region => {
        const radius = SPHERE_R * Math.sqrt(1 - y * y)
        return {
          weight: TAU * radius,
          at: (k, n) => {
            const a = TAU * ((k + 0.5) / n)
            return point(radius * Math.cos(a), SPHERE_R * y, radius * Math.sin(a), radius * Math.cos(a), SPHERE_R * y, radius * Math.sin(a))
          },
        }
      }
      return [great(0), great(1), great(2), parallel(-0.5), parallel(0.5)]
    }
    case 'torus': {
      const meridians = [0, 1, 2, 3, 4, 5].map((q): Region => ({
        weight: TAU * TORUS_T,
        at: (k, n) => {
          const a = (q * TAU) / 6
          const v = TAU * ((k + 0.5) / n)
          const r = TORUS_R + TORUS_T * Math.cos(v)
          return point(r * Math.cos(a), TORUS_T * Math.sin(v), r * Math.sin(a), Math.cos(v) * Math.cos(a), Math.sin(v), Math.cos(v) * Math.sin(a))
        },
      }))
      const parallel = (v: number): Region => {
        const r = TORUS_R + TORUS_T * Math.cos(v)
        return {
          weight: TAU * r,
          at: (k, n) => {
            const a = TAU * ((k + 0.5) / n)
            return point(r * Math.cos(a), TORUS_T * Math.sin(v), r * Math.sin(a), Math.cos(v) * Math.cos(a), Math.sin(v), Math.cos(v) * Math.sin(a))
          },
        }
      }
      return [...meridians, parallel(0), parallel(Math.PI), parallel(Math.PI / 2), parallel((3 * Math.PI) / 2)]
    }
  }
}

/**
 * Exactly ``count`` points on a solid: over its surface, or along its edges when ``wireframe``.
 * They are shared among faces (or edges) by area (or length) and, inside each, follow a fixed
 * low-discrepancy sequence, so a stride through the list still covers the whole solid.
 */
export function sampleSolid(kind: SolidKind, wireframe: boolean, count: number): SolidPoint[] {
  if (!(count > 0)) return []
  const regions = wireframe ? edgeRegions(kind) : surfaceRegions(kind)
  const shares = allocate(count, regions.map((r) => r.weight))
  return regions.flatMap((region, i) => Array.from({ length: shares[i] }, (_, j) => region.at(j, shares[i])))
}

function mul(a: Mat3, b: Mat3): Mat3 {
  const out: number[] = []
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 3; c++) out.push(a[r * 3] * b[c] + a[r * 3 + 1] * b[3 + c] + a[r * 3 + 2] * b[6 + c])
  }
  return out as unknown as Mat3
}

const rotX = (a: number): Mat3 => [1, 0, 0, 0, Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a)]
const rotY = (a: number): Mat3 => [Math.cos(a), 0, Math.sin(a), 0, 1, 0, -Math.sin(a), 0, Math.cos(a)]
const rotZ = (a: number): Mat3 => [Math.cos(a), -Math.sin(a), 0, Math.sin(a), Math.cos(a), 0, 0, 0, 1]

/** A shape is seen from slightly above and to the side, so its depth reads even when it is still. */
export const VIEW_PITCH = 0.5
export const VIEW_YAW = 0.6
/** The idle turn, in radians per second: a full turn in about 20 s. */
export const IDLE_SPEED = 0.32

/** The idle turn at ``time`` seconds; held still (zero) under reduced motion. */
export function idleTurn(time: number, reducedMotion: boolean): number {
  return reducedMotion ? 0 : time * IDLE_SPEED
}

/**
 * The turn that shows a shape: the scene's rotation (``rx`` then ``ry`` then ``rz``, in turns),
 * then the turntable (view yaw plus the idle turn) and the view pitch. A pure function of the
 * scene state and the idle angle, so going back a step gives back the earlier pose.
 */
export function solidMatrix(pose: SolidPose, idle: number): Mat3 {
  const scene = mul(rotZ(pose.rz * TAU), mul(rotY(pose.ry * TAU), rotX(pose.rx * TAU)))
  return mul(rotX(VIEW_PITCH), mul(rotY(VIEW_YAW + idle), scene))
}

export function applyMatrix(m: Mat3, x: number, y: number, z: number): [number, number, number] {
  return [m[0] * x + m[1] * y + m[2] * z, m[3] * x + m[4] * y + m[5] * z, m[6] * x + m[7] * y + m[8] * z]
}

/**
 * Front or side, decided per point from where its surface normal points after the turn: a normal
 * turned toward the viewer (z at most -SIDE_COS, z grows away from the viewer) is the front, in
 * the palette's main colour; everything else, including the far side, is a side, in the second
 * colour. The tag changes as the solid turns, so the face toward the viewer always reads as the
 * front and the body reads as a volume.
 */
export const SIDE_COS = 0.3
export function isSide(turnedNormalZ: number): boolean {
  return turnedNormalZ > -SIDE_COS
}
