import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { PushToTalkControl } from './PushToTalkControl'

describe('PushToTalkControl', () => {
  it('is a square icon-only button named for assistive technology', () => {
    render(<PushToTalkControl />)
    const button = screen.getByRole('button', { name: 'Hold to speak (or Space)' })

    expect(button).toHaveAttribute('data-shape', 'square')
    expect(button.textContent).toBe('')
    expect(button.querySelector('svg')).not.toBeNull()
  })

  it('toggles talking state with mouse down and up', () => {
    const onTalkingChange = vi.fn()
    render(<PushToTalkControl onTalkingChange={onTalkingChange} />)

    const btn = screen.getByTestId('ptt-button')
    expect(btn).toHaveAttribute('data-talking', 'false')

    fireEvent.mouseDown(btn)
    expect(btn).toHaveAttribute('data-talking', 'true')
    expect(onTalkingChange).toHaveBeenCalledWith(true)

    fireEvent.mouseUp(btn)
    expect(btn).toHaveAttribute('data-talking', 'false')
    expect(onTalkingChange).toHaveBeenCalledWith(false)
  })

  it('preserves touch holds and releases on touch end or cancellation', () => {
    const onTalkingChange = vi.fn()
    render(<PushToTalkControl onTalkingChange={onTalkingChange} />)
    const button = screen.getByRole('button', { name: 'Hold to speak (or Space)' })

    fireEvent.touchStart(button)
    expect(button).toHaveAttribute('aria-pressed', 'true')
    fireEvent.touchEnd(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
    fireEvent.touchStart(button)
    fireEvent.touchCancel(button)
    expect(button).toHaveAttribute('aria-pressed', 'false')
    expect(onTalkingChange.mock.calls).toEqual([[true], [false], [true], [false]])
  })

  it('toggles talking state with Space keydown and keyup', () => {
    const onTalkingChange = vi.fn()
    render(<PushToTalkControl onTalkingChange={onTalkingChange} />)

    const btn = screen.getByTestId('ptt-button')

    fireEvent.keyDown(window, { code: 'Space' })
    expect(btn).toHaveAttribute('data-talking', 'true')
    expect(onTalkingChange).toHaveBeenCalledWith(true)

    fireEvent.keyUp(window, { code: 'Space' })
    expect(btn).toHaveAttribute('data-talking', 'false')
    expect(onTalkingChange).toHaveBeenCalledWith(false)
  })

  it('prevents scrolling throughout a Space hold, including repeated keydowns', () => {
    const onTalkingChange = vi.fn()
    render(<PushToTalkControl onTalkingChange={onTalkingChange} />)

    expect(fireEvent.keyDown(window, { code: 'Space' })).toBe(false)
    expect(fireEvent.keyDown(window, { code: 'Space', repeat: true })).toBe(false)
    expect(screen.getByRole('button', { name: 'Transcribing answer...' })).toBeVisible()
    expect(onTalkingChange.mock.calls).toEqual([[true]])
    expect(fireEvent.keyUp(window, { code: 'Space' })).toBe(false)
    expect(onTalkingChange.mock.calls).toEqual([[true], [false]])
    expect(screen.getByRole('button', { name: 'Hold to speak (or Space)' })).toBeVisible()
  })

  it('ends an existing Space hold when focus moves into an input', () => {
    const onTalkingChange = vi.fn()
    render(<><input aria-label="Answer" /><PushToTalkControl onTalkingChange={onTalkingChange} /></>)
    fireEvent.keyDown(window, { code: 'Space' })
    fireEvent.keyUp(screen.getByRole('textbox', { name: 'Answer' }), { code: 'Space' })
    expect(onTalkingChange.mock.calls).toEqual([[true], [false]])
    expect(screen.getByRole('button', { name: 'Hold to speak (or Space)' })).toBeVisible()
  })

  it('starts a hold when Space auto-repeats inside a text field, and the release ends it', () => {
    const onTalkingChange = vi.fn()
    render(<><textarea aria-label="Answer" /><PushToTalkControl onTalkingChange={onTalkingChange} /></>)
    const field = screen.getByRole('textbox', { name: 'Answer' })

    expect(fireEvent.keyDown(field, { code: 'Space' })).toBe(true)
    expect(onTalkingChange).not.toHaveBeenCalled()
    expect(fireEvent.keyDown(field, { code: 'Space', repeat: true })).toBe(false)
    expect(fireEvent.keyDown(field, { code: 'Space', repeat: true })).toBe(false)
    expect(onTalkingChange.mock.calls).toEqual([[true]])
    expect(screen.getByTestId('ptt-button')).toHaveAttribute('data-talking', 'true')

    fireEvent.keyUp(field, { code: 'Space' })
    expect(onTalkingChange.mock.calls).toEqual([[true], [false]])
  })

  it('ignores Space key if focused inside an input element', () => {
    const onTalkingChange = vi.fn()
    render(
      <div>
        <input data-testid="test-input" />
        <PushToTalkControl onTalkingChange={onTalkingChange} />
      </div>
    )

    const input = screen.getByTestId('test-input')
    const btn = screen.getByTestId('ptt-button')

    expect(fireEvent.keyDown(input, { code: 'Space' })).toBe(true)
    expect(fireEvent.keyUp(input, { code: 'Space' })).toBe(true)
    expect(btn).toHaveAttribute('data-talking', 'false')
    expect(onTalkingChange).not.toHaveBeenCalled()
  })
})
