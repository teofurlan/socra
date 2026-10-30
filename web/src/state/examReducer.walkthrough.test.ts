import { describe, it, expect } from 'vitest'
import { examReducer, initialExamState } from './examReducer'

const started = examReducer(initialExamState, {
  type: 'walkthrough',
  title: 'Adding',
  objects: [{ id: 'code', primitive: 'code', params: { code: 'a = 1\nb = 2', language: 'python' }, hidden: false }],
  total: 2,
})

describe('examReducer walkthrough', () => {
  it('starts a walkthrough with no step focused yet', () => {
    expect(started.walkthrough).toEqual({
      title: 'Adding',
      objects: [{ id: 'code', primitive: 'code', params: { code: 'a = 1\nb = 2', language: 'python' }, hidden: false }],
      total: 2,
      step: null,
      status: 'playing',
      reason: null,
    })
  })

  it('focuses a step when the server reports it', () => {
    const state = { code: { visible: true, lines: [2, 2] } }
    const next = examReducer(started, { type: 'walkthrough_step', index: 2, total: 2, id: 's2', say: 'Now b.', state })
    expect(next.walkthrough?.step).toEqual({ index: 2, total: 2, id: 's2', say: 'Now b.', state })
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
    expect(examReducer(initialExamState, { type: 'walkthrough_step', index: 1, total: 1, id: 's1', say: 'x', state: {} })).toBe(initialExamState)
    expect(examReducer(initialExamState, { type: 'walkthrough_status', status: 'paused' })).toBe(initialExamState)
  })

  it('a new question or the end of the exam clears the walkthrough', () => {
    const asked = examReducer(started, { type: 'question', index: 1, total: 3, text: 'Why?' })
    expect(asked.walkthrough).toBeNull()
    expect(examReducer(started, { type: 'finished' }).walkthrough).toBeNull()
  })

  it('keeps the question that was on screen while the walkthrough runs', () => {
    const asked = examReducer(initialExamState, { type: 'question', index: 1, total: 3, text: 'Why?' })
    expect(examReducer(asked, { type: 'walkthrough', title: 'x', objects: [], total: 1 }).question?.text).toBe('Why?')
  })
})
