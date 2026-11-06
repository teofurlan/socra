import React from 'react'
import { orbColors } from '@/components/orbPalettes'
import { ParticleVisualizer } from '@/components/ParticleVisualizer'
import { DEFAULT_SHAPE, type ShapeId } from '@/components/visualizers'
import type { FigureSource } from '@/lib/sceneFigures'
import type { ProtocolState } from '@/types/exam'

export interface OrbVisualizerProps {
  protocolState: ProtocolState
  className?: string
  paletteId?: string
  getOutputVolume?: () => number
  getInputVolume?: () => number
  /** What the particles gather into. */
  shape?: ShapeId
  theme?: 'light' | 'dark'
  /** Keep the particles gathered while idle, as the focal point of a screen with no voice yet. */
  resting?: boolean
  /** What the particles assemble besides the voice shape while a scene plays. */
  figures?: FigureSource[]
}

export const OrbVisualizer: React.FC<OrbVisualizerProps> = ({
  protocolState,
  className = '',
  paletteId = 'state',
  getOutputVolume,
  getInputVolume,
  shape = DEFAULT_SHAPE,
  theme = 'dark',
  resting = false,
  figures,
}) => (
  <div
    data-testid="orb-visualizer"
    data-protocol-state={protocolState}
    className={`relative flex min-w-0 w-full items-center justify-center ${className}`}
  >
    <div className="relative aspect-square w-[min(100%,34vh,20rem)] supports-[height:100dvh]:w-[min(100%,34dvh,20rem)]">
      <ParticleVisualizer
        protocolState={protocolState}
        shape={shape}
        colors={orbColors(paletteId, protocolState, theme)}
        lightBackground={theme === 'light'}
        getOutputVolume={getOutputVolume}
        getInputVolume={getInputVolume}
        resting={resting}
        figures={figures}
        className="w-full h-full"
      />
    </div>
  </div>
)
