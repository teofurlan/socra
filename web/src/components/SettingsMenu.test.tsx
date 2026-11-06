import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SettingsMenu, type SettingsMenuProps } from '@/components/SettingsMenu'

function renderMenu(overrides: Partial<SettingsMenuProps> = {}) {
  const props: SettingsMenuProps = {
    mode: 'auto',
    onModeChange: vi.fn(),
    silenceTimeoutMs: 3000,
    onSilenceChange: vi.fn(),
    paletteId: 'state',
    onPaletteChange: vi.fn(),
    shape: 'sphere',
    onShapeChange: vi.fn(),
    themePref: 'system',
    onThemeChange: vi.fn(),
    microphones: [
      { deviceId: 'headset', label: 'Headset' },
      { deviceId: 'usb', label: 'USB Mic' },
    ],
    micDeviceId: '',
    onMicChange: vi.fn(),
    micFallback: false,
    onOpen: vi.fn(),
    ...overrides,
  }
  render(<SettingsMenu {...props} />)
  fireEvent.click(screen.getByTestId('settings-button'))
  return props
}

describe('SettingsMenu — microphone', () => {
  it('lists the system default and every available microphone', () => {
    renderMenu()
    const list = screen.getByRole('radiogroup', { name: 'Microphone' })
    expect(Array.from(list.querySelectorAll('[role="radio"]')).map((o) => o.getAttribute('aria-label'))).toEqual([
      'System default',
      'Headset',
      'USB Mic',
    ])
    expect(screen.getByRole('radio', { name: 'System default' })).toBeChecked()
  })

  it('reports the chosen microphone', () => {
    const props = renderMenu()
    fireEvent.click(screen.getByRole('radio', { name: 'USB Mic' }))
    expect(props.onMicChange).toHaveBeenCalledWith('usb')
  })

  it('shows the selected microphone', () => {
    renderMenu({ micDeviceId: 'usb' })
    expect(screen.getByRole('radio', { name: 'USB Mic' })).toBeChecked()
  })

  it('refreshes the device list each time it opens', () => {
    const props = renderMenu()
    expect(props.onOpen).toHaveBeenCalledOnce()
  })

  it('says when the selected microphone is disconnected', () => {
    renderMenu({ micDeviceId: 'gone' })
    expect(screen.getByRole('radio', { name: 'Disconnected microphone' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Disconnected microphone' })).toBeDisabled()
    expect(screen.getByTestId('mic-fallback-note')).toHaveTextContent(/system default/i)
  })

  it('says when capture fell back to the system default', () => {
    renderMenu({ micDeviceId: 'usb', micFallback: true })
    expect(screen.getByTestId('mic-fallback-note')).toHaveTextContent(/system default/i)
  })

  it('shows no note while the selected microphone works', () => {
    renderMenu({ micDeviceId: 'usb' })
    expect(screen.queryByTestId('mic-fallback-note')).toBeNull()
  })

  it('explains how to see device names before access is granted', () => {
    renderMenu({ microphones: [] })
    expect(screen.getByText(/allow microphone access/i)).toBeInTheDocument()
  })

  it('does not call a saved microphone disconnected while device names are hidden', () => {
    renderMenu({ microphones: [], micDeviceId: 'usb' })
    expect(screen.queryByRole('radio', { name: 'Disconnected microphone' })).toBeNull()
    expect(screen.queryByTestId('mic-fallback-note')).toBeNull()
  })
})

describe('SettingsMenu — theme', () => {
  it('offers system, light and dark, marking the current one, and reports a change', () => {
    const props = renderMenu({ themePref: 'system' })
    const group = screen.getByRole('radiogroup', { name: 'Theme' })
    expect(Array.from(group.querySelectorAll('[role="radio"]')).map((o) => o.textContent)).toEqual(['System', 'Light', 'Dark'])
    expect(screen.getByTestId('theme-system')).toHaveAttribute('aria-checked', 'true')

    fireEvent.click(screen.getByTestId('theme-light'))
    expect(props.onThemeChange).toHaveBeenCalledWith('light')
  })
})

describe('SettingsMenu — no look choice', () => {
  it('offers no visualizer look, keeping the shape and the particle colours', () => {
    renderMenu()
    expect(screen.queryByRole('radiogroup', { name: 'Visualizer' })).toBeNull()
    expect(screen.queryByText('Visualizer')).toBeNull()
    for (const id of ['particle-lines', 'particle-letters', 'particle-grid']) {
      expect(screen.queryByTestId(`visualizer-${id}`)).toBeNull()
    }
    expect(screen.getByRole('radiogroup', { name: 'Shape' })).toBeInTheDocument()
    expect(screen.getByText('Particle colors')).toBeInTheDocument()
  })
})

describe('SettingsMenu — shape', () => {
  it('offers the sphere and the sound wave, marking the current one', () => {
    renderMenu({ shape: 'wave' })
    const group = screen.getByRole('radiogroup', { name: 'Shape' })
    const options = Array.from(group.querySelectorAll('[role="radio"]'))
    expect(options.map((o) => o.textContent)).toEqual(['Sphere', 'Sound wave'])
    expect(screen.getByTestId('shape-wave')).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByTestId('shape-sphere')).toHaveAttribute('aria-checked', 'false')
  })

  it('reports the chosen shape', () => {
    const props = renderMenu()
    fireEvent.click(screen.getByTestId('shape-wave'))
    expect(props.onShapeChange).toHaveBeenCalledWith('wave')
  })

  it('hides the shape choice when nothing handles it', () => {
    renderMenu({ onShapeChange: undefined })
    expect(screen.queryByRole('radiogroup', { name: 'Shape' })).toBeNull()
  })
})

describe('SettingsMenu — voice', () => {
  it('shows a Voice section containing the voice picker when provided', () => {
    renderMenu({ voicePicker: <div data-testid="vp" /> })
    const section = screen.getByTestId('voice-control')
    expect(section).toBeInTheDocument()
    expect(section.querySelector('h2')).toHaveTextContent('Voice')
    expect(screen.getByTestId('vp')).toBeInTheDocument()
    expect(section).toContainElement(screen.getByTestId('vp'))
  })

  it('omits the voice-control section when voicePicker is not provided', () => {
    renderMenu()
    expect(screen.queryByTestId('voice-control')).toBeNull()
  })
})
