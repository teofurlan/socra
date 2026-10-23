import { describe, it, expect } from 'vitest'
import { examReducer, initialExamState } from './examReducer'

const started = examReducer(initialExamState, {
  type: 'walkthrough',
  code: 'a = 1\nb = 2',
  language: 'python',
  total: 2,
})

describe('examReducer walkthrough', () => {
  it('starts a walkthrough with no step focused yet', () => {
    expect(started.walkthrough).toEqual({
      code: 'a = 1\nb = 2',
      language: 'python',
      total: 2,
      step: null,
      status: 'playing',
      reason: null,
    })
  })

  it('focuses a step when the server reports it', () => {
    const next = examReducer(started, { type: 'walkthrough_step', index: 2, total: 2, say: 'Now b.', lines: [2, 2] })
    expect(next.walkthrough?.step).toEqual({ index: 2, total: 2, say: 'Now b.', lines: [2, 2] })
  })

  it('follows pause, resume and end', () => {
    const paused = examReducer(started, { type: 'walkthrough_status', status: 'paused' })
    expect(paused.walkthrough?.status).toBe('paused')
    const ended = examReducer(paused, { type: 'walkthrough_status', status: 'ended', reason: 'completed' })
    expect(ended.walkthrough).toMatchObject({ status: 'ended', reason: 'completed' })
    const resumed = examReducer(paused, { type: 'walkthrough_status', status: 'playing' })
    expect(resumed.walkthrough?.status).toBe('playing')
  })

  it('ignores step and status messages when no walkthrough is running', () => {
    expect(examReducer(initialExamState, { type: 'walkthrough_step', index: 1, total: 1, say: 'x', lines: null })).toBe(initialExamState)
    expect(examReducer(initialExamState, { type: 'walkthrough_status', status: 'paused' })).toBe(initialExamState)
  })

  it('a new question or the end of the exam clears the walkthrough', () => {
    const asked = examReducer(started, { type: 'question', index: 1, total: 3, text: 'Why?' })
    expect(asked.walkthrough).toBeNull()
    expect(examReducer(started, { type: 'finished' }).walkthrough).toBeNull()
  })

  it('keeps the question that was on screen while the walkthrough runs', () => {
    const asked = examReducer(initialExamState, { type: 'question', index: 1, total: 3, text: 'Why?' })
    expect(examReducer(asked, { type: 'walkthrough', code: 'x', language: '', total: 1 }).question?.text).toBe('Why?')
  })
})
