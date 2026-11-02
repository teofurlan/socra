import React from 'react'
import { orbColors } from '@/components/orbPalettes'
import { ParticleVisualizer } from '@/components/ParticleVisualizer'
import { DEFAULT_SHAPE, DEFAULT_VISUALIZER, type ShapeId, type VisualizerId } from '@/components/visualizers'
import type { ParticleStyle } from '@/lib/particleField'
import type { FigureSource } from '@/lib/sceneFigures'
import type { ProtocolState } from '@/types/exam'

const STYLE: Record<VisualizerId, ParticleStyle> = {
  'particle-lines': 'lines',
  'particle-letters': 'letters',
  'particle-grid': 'grid',
}

export interface OrbVisualizerProps {
  protocolState: ProtocolState
  className?: string
  paletteId?: string
  getOutputVolume?: () => number
  getInputVolume?: () => number
  visualizer?: VisualizerId
  /** What the particles gather into. */
  shape?: ShapeId
  /** The current question; the letter looks are made of its characters. */
  questionText?: string
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
  visualizer = DEFAULT_VISUALIZER,
  shape = DEFAULT_SHAPE,
  questionText,
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
        style={STYLE[visualizer]}
        shape={shape}
        colors={orbColors(paletteId, protocolState, theme)}
        lightBackground={theme === 'light'}
        getOutputVolume={getOutputVolume}
        getInputVolume={getInputVolume}
        letters={questionText}
        resting={resting}
        figures={figures}
        className="w-full h-full"
      />
    </div>
  </div>
)
