/**
 * Turns what a scene shows into figure points for the particle field: words rasterized to a
 * mask and sampled, or the outline of a box. Points are normalised to 0..1 of their box, so
 * the field can place them over whatever element they belong to, frame by frame.
 */
import type { FigurePoint } from '@/lib/particleField'

/** RGBA pixels, as ``CanvasRenderingContext2D.getImageData`` returns them. */
export interface Mask {
  width: number
  height: number
  data: Uint8ClampedArray
}

const OPAQUE = 128

function sample(mask: Mask, stride: number): FigurePoint[] {
  const { width, height, data } = mask
  const points: FigurePoint[] = []
  const start = Math.floor(stride / 2)
  for (let y = start; y < height; y += stride) {
    // Every other row shifts by half a step, so the points sit on a staggered, even grid.
    const shift = (Math.floor(y / stride) % 2) * Math.floor(stride / 2)
    for (let x = start + shift; x < width; x += stride) {
      if (data[(y * width + x) * 4 + 3] >= OPAQUE) points.push({ x: (x + 0.5) / width, y: (y + 0.5) / height })
    }
  }
  return points
}

/**
 * Points on the opaque pixels of a mask, at most ``max`` of them, spread over the whole shape
 * on an even grid whose step grows until they fit.
 */
export function pointsFromMask(mask: Mask, max: number): FigurePoint[] {
  if (max <= 0) return []
  let opaque = 0
  for (let i = 3; i < mask.data.length; i += 4) if (mask.data[i] >= OPAQUE) opaque++
  if (opaque === 0) return []
  let stride = Math.max(1, Math.floor(Math.sqrt(opaque / max)))
  let points = sample(mask, stride)
  while (points.length > max) points = sample(mask, ++stride)
  return points
}

/**
 * ``count`` points around the edge of a ``width`` x ``height`` box, evenly spaced in pixels and
 * going clockwise from the top-left corner; each lies along the edge it sits on.
 */
export function outlinePoints(count: number, width: number, height: number): FigurePoint[] {
  const perimeter = 2 * (width + height)
  if (count <= 0 || perimeter <= 0) return []
  const points: FigurePoint[] = []
  for (let k = 0; k < count; k++) {
    let d = ((k + 0.5) / count) * perimeter
    if (d < width) {
      points.push({ x: d / width, y: 0, a: 0 })
      continue
    }
    d -= width
    if (d < height) {
      points.push({ x: 1, y: d / height, a: Math.PI / 2 })
      continue
    }
    d -= height
    if (d < width) {
      points.push({ x: 1 - d / width, y: 1, a: 0 })
      continue
    }
    d -= width
    points.push({ x: 0, y: Math.max(0, 1 - d / height), a: Math.PI / 2 })
  }
  return points
}

/** Height in pixels words are rasterized at; the figure is scaled to its box afterwards. */
const RASTER_HEIGHT = 96

/**
 * Rasterizes ``text`` on a hidden canvas and samples it. Returns the points and the text's
 * aspect ratio (width / height), so its box can keep the letters' proportions; ``null``
 * where there is no 2D canvas (tests, very old browsers).
 */
export function textFigure(text: string, max: number, fontFamily: string): { points: FigurePoint[]; aspect: number } | null {
  try {
    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d', { willReadFrequently: true })
    if (!ctx) return null
    const font = `700 ${RASTER_HEIGHT * 0.78}px ${fontFamily}`
    ctx.font = font
    const width = Math.max(1, Math.ceil(ctx.measureText(text).width) + 8)
    canvas.width = width
    canvas.height = RASTER_HEIGHT
    // Resizing the canvas resets its state, so the font is set again before drawing.
    ctx.font = font
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#000'
    ctx.fillText(text, 4, RASTER_HEIGHT / 2)
    const image = ctx.getImageData(0, 0, width, RASTER_HEIGHT)
    return { points: pointsFromMask(image, max), aspect: width / RASTER_HEIGHT }
  } catch {
    return null
  }
}
