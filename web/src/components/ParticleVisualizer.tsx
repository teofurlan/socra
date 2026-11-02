import React, { useEffect, useRef } from 'react'
import {
  ParticleField,
  lettersFrom,
  particleCount,
  simulatedVoice,
  type FieldShape,
  type Figure,
  type FigurePoint,
  type FieldState,
  type ParticleStyle,
} from '@/lib/particleField'
import type { FigureSource } from '@/lib/sceneFigures'

export interface ParticleVisualizerProps {
  protocolState: FieldState
  style: ParticleStyle
  /** Sphere or sound wave; switching it moves the particles without rebuilding them. */
  shape?: FieldShape
  colors: [string, string]
  getOutputVolume?: () => number
  getInputVolume?: () => number
  /** Text the "letters" look is made of, usually the current question. */
  letters?: string
  /** The page ground is light: paint particles instead of adding light. */
  lightBackground?: boolean
  /** While idle, keep the particles gathered in their shape, small and slow. */
  resting?: boolean
  /** What the particles assemble besides the voice shape, such as a scene's focused lines. */
  figures?: FigureSource[]
  className?: string
}

const NO_FIGURES: FigureSource[] = []

/**
 * Holds the visualizer's slot in the layout and paints a screen-wide canvas behind the
 * content: particles roam the whole screen and gather into a sphere in this slot. A second
 * canvas above the content carries only the particles that point at something.
 */
export const ParticleVisualizer: React.FC<ParticleVisualizerProps> = ({
  protocolState,
  style,
  shape = 'sphere',
  colors,
  getOutputVolume,
  getInputVolume,
  letters,
  lightBackground = false,
  resting = false,
  figures = NO_FIGURES,
  className = '',
}) => {
  const slotRef = useRef<HTMLDivElement>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const frontRef = useRef<HTMLCanvasElement>(null)
  const fieldRef = useRef<ParticleField | null>(null)
  const live = useRef({ protocolState, colors, getOutputVolume, getInputVolume, lightBackground, resting, figures })
  live.current = { protocolState, colors, getOutputVolume, getInputVolume, lightBackground, resting, figures }

  useEffect(() => {
    const canvas = canvasRef.current
    const slot = slotRef.current
    const front = frontRef.current
    const context = (c: HTMLCanvasElement | null) => {
      try {
        return c?.getContext('2d') ?? null
      } catch {
        return null
      }
    }
    const ctx = context(canvas)
    const frontCtx = context(front)
    if (!canvas || !front || !slot || !ctx || !frontCtx) return

    const field = new ParticleField({
      count: particleCount(window.innerWidth, window.innerHeight),
      style,
      shape,
      letters: lettersFrom(letters),
    })
    fieldRef.current = field
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

    let dpr = 1
    const resize = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1)
      for (const c of [canvas, front]) {
        c.width = Math.round(window.innerWidth * dpr)
        c.height = Math.round(window.innerHeight * dpr)
      }
      field.resize(window.innerWidth, window.innerHeight)
      const count = particleCount(window.innerWidth, window.innerHeight)
      if (Math.abs(count - field.particles.length) > 150) field.setCount(count)
    }
    resize()
    window.addEventListener('resize', resize)

    // Each figure's points, built from the first box it is seen in and kept while its id lives.
    const built = new Map<string, FigurePoint[]>()
    const frameFigures = (): Figure[] => {
      const out: Figure[] = []
      const ids = new Set<string>()
      for (const source of live.current.figures) {
        ids.add(source.id)
        const box = source.box()
        if (!box) continue
        let points = built.get(source.id)
        if (!points) {
          points = source.build(box)
          built.set(source.id, points)
        }
        out.push({ id: source.id, points, box, role: source.role })
      }
      for (const id of built.keys()) if (!ids.has(id)) built.delete(id)
      return out
    }

    let raf = 0
    let last = performance.now() / 1000
    const frame = () => {
      const now = performance.now() / 1000
      const dt = Math.min(1 / 30, now - last)
      last = now
      const { protocolState: state, colors: c, getOutputVolume: out, getInputVolume: inp } = live.current
      const volume =
        state === 'speaking' ? (out ? out() : simulatedVoice(now))
        : state === 'listening' ? (inp ? inp() : simulatedVoice(now + 7))
        : state === 'thinking' ? 0.14 + 0.08 * Math.sin(now * 2.2)
        : 0
      const rect = slot.getBoundingClientRect()
      field.setColors(c)
      field.setLightBackground(live.current.lightBackground)
      field.step({
        dt,
        time: now,
        width: window.innerWidth,
        height: window.innerHeight,
        cx: rect.left + rect.width / 2,
        cy: rect.top + rect.height / 2,
        radius: Math.min(rect.width, rect.height) / 2,
        state,
        volume,
        reducedMotion,
        rest: live.current.resting,
        figures: frameFigures(),
      })
      field.draw(ctx, dpr, 'back')
      field.draw(frontCtx, dpr, 'front')
      raf = requestAnimationFrame(frame)
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      fieldRef.current = null
    }
    // The letters and the shape are applied by the effects below without rebuilding the field.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [style])

  useEffect(() => {
    fieldRef.current?.setLetters(lettersFrom(letters))
  }, [letters])

  useEffect(() => {
    fieldRef.current?.setShape(shape)
  }, [shape])

  return (
    <div ref={slotRef} data-testid="particle-visualizer" data-style={style} data-shape={shape} data-resting={resting} data-figures={figures.map((f) => f.id).join(' ')} className={className}>
      <canvas
        ref={canvasRef}
        data-layer="back"
        aria-hidden
        className="pointer-events-none fixed inset-0 -z-10 h-full w-full"
      />
      {/* Over the panels (z-index 1 headers, opaque code pane) but under menus and popovers (z-30), so particles outlining focused lines stay visible. */}
      <canvas
        ref={frontRef}
        data-layer="front"
        aria-hidden
        className="pointer-events-none fixed inset-0 z-20 h-full w-full"
      />
    </div>
  )
}
