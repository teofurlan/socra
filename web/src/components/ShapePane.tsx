import { useEffect, useRef } from 'react'
import { X } from 'lucide-react'
import Zdog from 'zdog'
import { Panel } from '@/components/shell/Panel'

export interface ShapePaneProps {
  id: string
  shape: 'cube' | 'cylinder' | 'cone' | 'sphere' | 'torus'
  color?: string
  wireframe?: boolean
  rx?: number
  ry?: number
  rz?: number
  onClose?: () => void
}

const DEFAULT_COLORS = {
  cube: {
    base: '#00f0ff',
    left: '#00c8d4',
    right: '#0096a0',
    top: '#66f5ff',
    bottom: '#00646b',
  },
  cylinder: '#ffaa00',
  cone: '#ff9044',
  sphere: '#00f0ff',
  torus: '#38bdf8',
}

/** Renders a 3D geometric solid on the Stage using lightweight Zdog canvas rendering. */
export function ShapePane({
  id,
  shape,
  color,
  wireframe = false,
  rx = 0,
  ry = 0,
  rz = 0,
  onClose,
}: ShapePaneProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const illoRef = useRef<Zdog.Illustration | null>(null)
  const targetRotation = useRef({ x: rx * Math.PI * 2, y: ry * Math.PI * 2, z: rz * Math.PI * 2 })

  // Keep target rotation updated on step changes
  useEffect(() => {
    targetRotation.current = {
      x: rx * Math.PI * 2,
      y: ry * Math.PI * 2,
      z: rz * Math.PI * 2,
    }
  }, [rx, ry, rz])

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    // Safely check for 2D context (jsdom in tests returns null without canvas package)
    const ctx = canvas.getContext?.('2d')
    if (!ctx) return

    // Set canvas dimensions
    const size = 320
    canvas.width = size * window.devicePixelRatio
    canvas.height = size * window.devicePixelRatio
    canvas.style.width = `${size}px`
    canvas.style.height = `${size}px`

    const illo = new Zdog.Illustration({
      element: canvas,
      zoom: 1,
      dragRotate: true,
      rotate: {
        x: targetRotation.current.x,
        y: targetRotation.current.y,
        z: targetRotation.current.z,
      },
    })
    illoRef.current = illo

    // Build the geometric shape
    const baseColor = color || DEFAULT_COLORS[shape] || '#00f0ff'

    if (shape === 'cube') {
      new Zdog.Box({
        addTo: illo,
        width: 110,
        height: 110,
        depth: 110,
        stroke: wireframe ? 2 : false,
        fill: !wireframe,
        color: typeof baseColor === 'string' ? baseColor : DEFAULT_COLORS.cube.base,
        leftFace: wireframe ? undefined : DEFAULT_COLORS.cube.left,
        rightFace: wireframe ? undefined : DEFAULT_COLORS.cube.right,
        topFace: wireframe ? undefined : DEFAULT_COLORS.cube.top,
        bottomFace: wireframe ? undefined : DEFAULT_COLORS.cube.bottom,
      })
    } else if (shape === 'cylinder') {
      new Zdog.Cylinder({
        addTo: illo,
        diameter: 110,
        length: 110,
        stroke: wireframe ? 2 : false,
        fill: !wireframe,
        color: typeof baseColor === 'string' ? baseColor : DEFAULT_COLORS.cylinder,
      })
    } else if (shape === 'cone') {
      new Zdog.Cone({
        addTo: illo,
        diameter: 110,
        length: 110,
        stroke: wireframe ? 2 : false,
        fill: !wireframe,
        color: typeof baseColor === 'string' ? baseColor : DEFAULT_COLORS.cone,
      })
    } else if (shape === 'sphere') {
      new Zdog.Shape({
        addTo: illo,
        stroke: 110,
        color: typeof baseColor === 'string' ? baseColor : DEFAULT_COLORS.sphere,
      })
    } else if (shape === 'torus') {
      new Zdog.Ellipse({
        addTo: illo,
        diameter: 100,
        stroke: 26,
        fill: false,
        color: typeof baseColor === 'string' ? baseColor : DEFAULT_COLORS.torus,
      })
    }

    let isRunning = true
    function animate() {
      if (!isRunning) return
      // Smoothly interpolate towards target rotation if not dragging
      if (illo) {
        illo.rotate.x += (targetRotation.current.x - illo.rotate.x) * 0.1
        illo.rotate.y += (targetRotation.current.y - illo.rotate.y) * 0.1
        illo.rotate.z += (targetRotation.current.z - illo.rotate.z) * 0.1
        illo.updateRenderGraph()
      }
      requestAnimationFrame(animate)
    }

    animate()

    return () => {
      isRunning = false
    }
  }, [shape, color, wireframe])

  return (
    <Panel
      label={`3D shape: ${shape}`}
      testId="shape-pane"
      className="h-full"
      title={<span>3D Shape</span>}
      meta={
        <>
          <span className="t-mono truncate uppercase tracking-wider text-xs" style={{ color: 'var(--label-3)' }}>
            {shape} {wireframe ? '· wireframe' : ''}
          </span>
          {onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close shape"
              title="Close the shape panel"
              className="-mr-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md hover:bg-[var(--raise)] hover:text-[var(--label)]"
              style={{ color: 'var(--label-2)' }}
            >
              <X aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
            </button>
          )}
        </>
      }
    >
      <div
        data-scene-object={id}
        className="flex flex-1 items-center justify-center p-6 select-none relative overflow-hidden"
      >
        <canvas
          ref={canvasRef}
          className="cursor-grab active:cursor-grabbing rounded-lg"
          aria-label={`Interactive 3D ${shape}`}
        />
        <div
          className="absolute bottom-3 text-center text-xs pointer-events-none opacity-60"
          style={{ color: 'var(--label-3)' }}
        >
          Drag to spin
        </div>
      </div>
    </Panel>
  )
}
