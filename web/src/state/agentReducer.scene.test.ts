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

  it('drops an ended scene when the agent replies, so the reply code can take the pane', () => {
    const ended = run(scene, step, { type: 'walkthrough_status', status: 'ended', reason: 'completed' })
    expect(agentReducer(ended, { type: 'agent_reply', text: 'Done.' }).walkthrough).toBeNull()
    const playing = run(scene, step)
    expect(agentReducer(playing, { type: 'agent_reply', text: 'Still going.' }).walkthrough).not.toBeNull()
  })
})
