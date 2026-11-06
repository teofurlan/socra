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

  it('keeps the scene while the user steers it, and drops an ended scene at the next turn', () => {
    const playing = run(scene, step, { type: 'transcript', text: 'pause', final: true })
    expect(playing.walkthrough?.status).toBe('playing')

    const ended = agentReducer(playing, { type: 'walkthrough_status', status: 'ended', reason: 'completed' })
    expect(ended.walkthrough?.reason).toBe('completed')
    expect(agentReducer(ended, { type: 'user_text', text: 'thanks' }).walkthrough).toBeNull()
    expect(agentReducer(ended, { type: 'transcript', text: 'thanks', final: true }).walkthrough).toBeNull()
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

  it('releases a completed scene at the user turn, typed or spoken', () => {
    const ended = run(scene, step, completed)
    expect(agentReducer(ended, { type: 'user_text', text: 'why?' }).walkthrough).toBeNull()
    expect(agentReducer(ended, { type: 'transcript', text: 'why?', final: true }).walkthrough).toBeNull()
    expect(agentReducer(ended, { type: 'transcript', text: 'wh', final: false }).walkthrough).not.toBeNull()
  })

  it('a new scene replaces the held one', () => {
    const next: AgentAction = { type: 'walkthrough', title: 'Next', objects, total: 1 }
    expect(run(scene, step, completed, next).walkthrough).toMatchObject({ title: 'Next', status: 'playing', step: null })
  })
})
