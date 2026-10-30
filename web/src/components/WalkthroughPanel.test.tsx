import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { WalkthroughPanel } from './WalkthroughPanel'
import type { WalkthroughData } from '@/types/exam'

const base: WalkthroughData = {
  title: 'Adding',
  objects: [],
  total: 3,
  status: 'playing',
  reason: null,
  step: { index: 2, total: 3, id: 'add', say: 'Now we add them.', state: {} },
}

describe('WalkthroughPanel', () => {
  it('shows the step being spoken and where it is in the walkthrough', () => {
    render(<WalkthroughPanel walkthrough={base} onControl={vi.fn()} />)
    expect(screen.getByText('Now we add them.')).toBeInTheDocument()
    expect(screen.getByTestId('walkthrough-progress')).toHaveTextContent('Step 2/3')
  })

  it('sends each control as an action', async () => {
    const user = userEvent.setup()
    const onControl = vi.fn()
    render(<WalkthroughPanel walkthrough={base} onControl={onControl} />)

    await user.click(screen.getByRole('button', { name: 'Back' }))
    await user.click(screen.getByRole('button', { name: 'Repeat' }))
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Pause' }))
    await user.click(screen.getByRole('button', { name: 'Stop' }))

    expect(onControl.mock.calls.map(([action]) => action)).toEqual(['back', 'repeat', 'next', 'pause', 'stop'])
  })

  it('offers Resume and the spoken commands while paused', async () => {
    const user = userEvent.setup()
    const onControl = vi.fn()
    render(<WalkthroughPanel walkthrough={{ ...base, status: 'paused' }} onControl={onControl} />)

    expect(screen.queryByRole('button', { name: 'Pause' })).not.toBeInTheDocument()
    expect(screen.getByText(/repeat, back, next, continue or stop/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Resume' }))
    expect(onControl).toHaveBeenCalledWith('resume')
  })

  it('drops the controls when it is over and says how it ended', () => {
    render(<WalkthroughPanel walkthrough={{ ...base, status: 'ended', reason: 'stopped' }} onControl={vi.fn()} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Walkthrough stopped')
  })

  it('waits quietly before the first step is heard', () => {
    render(<WalkthroughPanel walkthrough={{ ...base, step: null }} onControl={vi.fn()} />)
    expect(screen.getByTestId('walkthrough-progress')).toHaveTextContent('Starting')
  })
})
