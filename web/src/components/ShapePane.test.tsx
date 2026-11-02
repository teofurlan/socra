import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ShapePane } from './ShapePane'

describe('ShapePane', () => {
  it('renders canvas with correct aria labels and shape title', () => {
    render(
      <ShapePane
        id="cube-1"
        shape="cube"
        color="#00f0ff"
        wireframe={false}
        rx={0}
        ry={0}
        rz={0}
        onClose={() => {}}
      />,
    )
    expect(screen.getByTestId('shape-pane')).toBeInTheDocument()
    expect(screen.getByText('3D Shape')).toBeInTheDocument()
    expect(screen.getByText(/cube/i)).toBeInTheDocument()
  })
})
