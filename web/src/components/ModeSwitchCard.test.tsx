import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ModeSwitchCard } from './ModeSwitchCard'

describe('ModeSwitchCard', () => {
  it('renders nothing without a request', () => {
    const { container } = render(<ModeSwitchCard request={null} onAnswer={vi.fn()} />)

    expect(container).toBeEmptyDOMElement()
  })

  it('asks the user to confirm a voice-requested switch and never switches by itself', async () => {
    const onAnswer = vi.fn()
    render(<ModeSwitchCard request={{ mode: 'exam', label: 'Exam' }} onAnswer={onAnswer} />)
    const user = userEvent.setup()

    expect(screen.getByRole('group', { name: 'Switch to Exam mode?' })).toBeInTheDocument()
    expect(onAnswer).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Switch' }))
    await user.click(screen.getByRole('button', { name: 'Not now' }))

    expect(onAnswer.mock.calls).toEqual([['exam', true], ['exam', false]])
  })
})
