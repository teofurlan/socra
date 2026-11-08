import { describe, it, expect } from 'vitest'
import { agentReducer, initialAgentState } from './agentReducer'
import type { AgentAction, AgentState } from '@/types/agent'

const run = (...actions: AgentAction[]): AgentState => actions.reduce(agentReducer, initialAgentState)

const objects = [{ id: 'src', primitive: 'code', params: { code: 'a\nb', language: 'python' }, hidden: false }]
const scene: AgentAction = { type: 'walkthrough', title: 'Adding', objects, total: 2 }
const step: AgentAction = {
  type: 'walkthrough_step', index: 1, total: 2, id: 'names', say: 'Two names.', state: { src: { visible: true, lines: [1, 2] } },
}

describe('agentReducer scenes', () => {
  it('starts a scene, follows its steps and its status', () => {
    const state = run(scene, step, { type: 'walkthrough_status', status: 'paused' })
    expect(state.walkthrough).toEqual({
      title: 'Adding',
      objects,
      total: 2,
      step: { index: 1, total: 2, id: 'names', say: 'Two names.', state: { src: { visible: true, lines: [1, 2] } } },
      status: 'paused',
      reason: null,
    })
  })

  it('ignores steps and status without a scene', () => {
    expect(run(step).walkthrough).toBeNull()
    expect(run({ type: 'walkthrough_status', status: 'ended', reason: 'completed' }).walkthrough).toBeNull()
  })

  it('keeps the scene while the user steers it, and an ended scene stays at the next turn', () => {
    const playing = run(scene, step, { type: 'transcript', text: 'pause', final: true })
    expect(playing.walkthrough?.status).toBe('playing')

    const ended = agentReducer(playing, { type: 'walkthrough_status', status: 'ended', reason: 'completed' })
    expect(ended.walkthrough?.reason).toBe('completed')
    expect(agentReducer(ended, { type: 'user_text', text: 'thanks' }).walkthrough?.status).toBe('ended')
    expect(agentReducer(ended, { type: 'transcript', text: 'thanks', final: true }).walkthrough?.status).toBe('ended')
  })

  const completed: AgentAction = { type: 'walkthrough_status', status: 'ended', reason: 'completed' }

  it('keeps a completed scene when the agent replies without code, so the last step stays up', () => {
    const ended = run(scene, step, completed)
    expect(agentReducer(ended, { type: 'agent_reply', text: 'Anything unclear?' }).walkthrough).toMatchObject({ status: 'ended', reason: 'completed' })
    const playing = run(scene, step)
    expect(agentReducer(playing, { type: 'agent_reply', text: 'Still going.' }).walkthrough).not.toBeNull()
  })

  it('drops an ended scene when the agent replies with code, so that code can take the pane', () => {
    const ended = run(scene, step, completed)
    const reply = { type: 'agent_reply', text: 'Try:\n```python\nx = 1\n```' } as const
    expect(agentReducer(ended, reply).walkthrough).toBeNull()
  })

  it('keeps a completed scene at the user turn, typed or spoken, so the check can point at it', () => {
    const ended = run(scene, step, completed)
    expect(agentReducer(ended, { type: 'user_text', text: 'why?' }).walkthrough).toMatchObject({ status: 'ended' })
    expect(agentReducer(ended, { type: 'transcript', text: 'why?', final: true }).walkthrough).toMatchObject({ status: 'ended' })
  })

  it('releases an ended scene when the agent clears it', () => {
    expect(run(scene, step, completed, { type: 'walkthrough_cleared' }).walkthrough).toBeNull()
  })

  it('ignores the clear while the scene still plays, and without a scene', () => {
    const playing = run(scene, step)
    expect(agentReducer(playing, { type: 'walkthrough_cleared' })).toBe(playing)
    expect(run({ type: 'walkthrough_cleared' }).walkthrough).toBeNull()
  })

  it('a new scene replaces the held one', () => {
    const next: AgentAction = { type: 'walkthrough', title: 'Next', objects, total: 1 }
    expect(run(scene, step, completed, next).walkthrough).toMatchObject({ title: 'Next', status: 'playing', step: null })
  })
})

describe('agentReducer pointing', () => {
  const completed: AgentAction = { type: 'walkthrough_status', status: 'ended', reason: 'completed' }
  const point = (...targets: { object: string; part?: string; lines?: [number, number] }[]): AgentAction => ({ type: 'walkthrough_point', targets })
  const target = { object: 'src', lines: [1, 2] as [number, number] }

  it('stores the targets on an ended scene', () => {
    expect(run(scene, step, completed, point(target)).walkthrough?.pointing).toEqual([target])
  })

  it('ignores them while the scene plays and when no scene is shown', () => {
    const playing = run(scene, step)
    expect(agentReducer(playing, point(target))).toBe(playing)
    expect(run(point(target)).walkthrough).toBeNull()
  })

  it('replaces the previous targets, and an empty list removes them', () => {
    const other = { object: 'src', lines: [2, 2] as [number, number] }
    const state = run(scene, step, completed, point(target), point(other))
    expect(state.walkthrough?.pointing).toEqual([other])
    expect(agentReducer(state, point()).walkthrough?.pointing).toBeUndefined()
  })

  it('drops them with the scene: cleared, or replaced by a new scene', () => {
    const pointed = run(scene, step, completed, point(target))
    expect(agentReducer(pointed, { type: 'walkthrough_cleared' }).walkthrough).toBeNull()
    const next = agentReducer(pointed, { type: 'walkthrough', title: 'Next', objects, total: 1 })
    expect(next.walkthrough?.pointing).toBeUndefined()
  })

  it('survives the user speaking, like the scene itself', () => {
    const pointed = run(scene, step, completed, point(target))
    expect(agentReducer(pointed, { type: 'user_text', text: 'two' }).walkthrough?.pointing).toEqual([target])
  })
})

describe('agentReducer prediction results and replays', () => {
  const completed: AgentAction = { type: 'walkthrough_status', status: 'ended', reason: 'completed' }
  const target = { object: 'src', lines: [1, 2] as [number, number] }
  const withArray = [
    ...objects,
    { id: 'arr', primitive: 'structure', params: { kind: 'array', items: [1, 2] }, hidden: false },
  ]
  const arrayScene: AgentAction = { type: 'walkthrough', title: 'Arr', objects: withArray, total: 1 }
  const arrayStep: AgentAction = {
    type: 'walkthrough_step', index: 1, total: 1, id: 'only', say: 'Two.',
    state: { src: { visible: true, lines: null }, arr: { visible: true, kind: 'array', items: [1, 2], last: null } },
  }
  const result: AgentAction = {
    type: 'walkthrough_result', object: 'arr',
    state: { visible: true, kind: 'array', items: [1, 9], last: { op: 'set', index: 1, value: 9, previous: 2 } },
  }

  it('applies a result to that object only, on an ended scene', () => {
    const state = run(arrayScene, arrayStep, completed, result)
    expect(state.walkthrough?.step?.state.arr).toMatchObject({ items: [1, 9], last: { op: 'set' } })
    expect(state.walkthrough?.step?.state.src).toEqual({ visible: true, lines: null })
    expect(state.walkthrough?.status).toBe('ended')
  })

  it('chains results and removes the pointing', () => {
    const next: AgentAction = { ...result, state: { ...(result as { state: object }).state, items: [1, 9, 3] } as never }
    const pointed = run(arrayScene, arrayStep, completed, { type: 'walkthrough_point', targets: [target] })
    expect(pointed.walkthrough?.pointing).toEqual([target])
    const state = [result, next].reduce(agentReducer, pointed)
    expect(state.walkthrough?.pointing).toBeUndefined()
    expect(state.walkthrough?.step?.state.arr).toMatchObject({ items: [1, 9, 3] })
  })

  it('ignores a result while the scene plays, with no scene or for an unknown object', () => {
    const playing = run(arrayScene, arrayStep)
    expect(agentReducer(playing, result)).toBe(playing)
    expect(run(result).walkthrough).toBeNull()
    const ended = run(arrayScene, arrayStep, completed)
    expect(agentReducer(ended, { ...result, object: 'nope' } as AgentAction)).toBe(ended)
  })

  it('shows a replayed step after the scene ended, ends on it and drops the pointing', () => {
    const second: AgentAction = { ...arrayStep, index: 1, id: 'again', say: 'Again.' } as AgentAction
    const pointed = run(arrayScene, arrayStep, completed, { type: 'walkthrough_point', targets: [target] })
    const state = [second, completed].reduce(agentReducer, pointed)
    expect(state.walkthrough).toMatchObject({ status: 'ended', reason: 'completed', step: { id: 'again' } })
    expect(state.walkthrough?.pointing).toBeUndefined()
  })
})
