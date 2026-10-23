import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModeSelector } from './ModeSelector'

describe('ModeSelector', () => {
  it('offers agent, mentor and exam with the current mode checked', () => {
    render(<ModeSelector mode="mentor" onChange={vi.fn()} />)

    const group = screen.getByRole('radiogroup', { name: /mode/i })
    expect(group).toBeInTheDocument()
    expect(screen.getAllByRole('radio').map((radio) => radio.textContent)).toEqual(['Agent', 'Mentor', 'Exam'])
    expect(screen.getByRole('radio', { name: 'Mentor' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Exam' })).not.toBeChecked()
  })

  it('switches when another mode is chosen, but not for the current one', async () => {
    const onChange = vi.fn()
    render(<ModeSelector mode="agent" onChange={onChange} />)
    const user = userEvent.setup()

    await user.click(screen.getByRole('radio', { name: 'Agent' }))
    expect(onChange).not.toHaveBeenCalled()
    await user.click(screen.getByRole('radio', { name: 'Exam' }))

    expect(onChange).toHaveBeenCalledExactlyOnceWith('exam')
  })

  it('is disabled with a visible reason when the backend cannot switch', () => {
    render(<ModeSelector mode="agent" onChange={vi.fn()} disabled reason="Mode switching needs Claude Code" />)

    for (const radio of screen.getAllByRole('radio')) expect(radio).toBeDisabled()
    expect(screen.getByText('Mode switching needs Claude Code')).toBeVisible()
    expect(screen.getByRole('radiogroup')).toHaveAccessibleDescription('Mode switching needs Claude Code')
  })

  it('shows the target while the handoff runs and takes no clicks', async () => {
    const onChange = vi.fn()
    render(<ModeSelector mode="agent" onChange={onChange} switching="exam" />)

    expect(screen.getByRole('radiogroup')).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Switching to Exam…')).toBeVisible()
    await userEvent.setup().click(screen.getByRole('radio', { name: 'Mentor' }))
    expect(onChange).not.toHaveBeenCalled()
  })
})
