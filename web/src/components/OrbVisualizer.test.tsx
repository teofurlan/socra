import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { OrbVisualizer } from './OrbVisualizer'

describe('OrbVisualizer', () => {
  it('draws the particle dots', () => {
    render(<OrbVisualizer protocolState="speaking" />)

    expect(screen.getByTestId('orb-visualizer')).toHaveAttribute('data-protocol-state', 'speaking')
    expect(screen.getByTestId('particle-visualizer')).not.toHaveAttribute('data-style')
  })

  it('forms the chosen shape, the sphere by default', () => {
    const { rerender } = render(<OrbVisualizer protocolState="speaking" />)
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'sphere')

    rerender(<OrbVisualizer protocolState="speaking" shape="wave" />)
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-shape', 'wave')
  })

  it('lets the particles rest in their shape only when asked', () => {
    const { rerender } = render(<OrbVisualizer protocolState="idle" />)
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-resting', 'false')

    rerender(<OrbVisualizer protocolState="idle" resting />)
    expect(screen.getByTestId('particle-visualizer')).toHaveAttribute('data-resting', 'true')
  })

  it('paints on two decorative screen canvases, one behind the content and one above it for pointing', () => {
    render(<OrbVisualizer protocolState="idle" />)
    const slot = screen.getByTestId('particle-visualizer')
    const back = slot.querySelector('canvas[data-layer="back"]')
    const front = slot.querySelector('canvas[data-layer="front"]')
    expect(back).toHaveClass('-z-10', 'pointer-events-none')
    expect(front).toHaveClass('z-20', 'pointer-events-none')
    for (const canvas of [back, front]) expect(canvas).toHaveAttribute('aria-hidden', 'true')
  })
})
