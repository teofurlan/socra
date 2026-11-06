import { Component, useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { Panel } from '@/components/shell/Panel'
import { sceneMetrics } from '@/lib/sceneMetrics'
import type { WalkthroughData } from '@/types/exam'
import { PRIMITIVE_RENDERERS, panelObjects, type PrimitiveRenderers } from '@/components/scene/registry'

/** The step's text in the panel, for a primitive that is unknown or failed to draw. */
function Fallback({ say, onClose }: { say: string; onClose: () => void }) {
  return (
    <Panel
      label="Scene"
      testId="scene-fallback"
      className="h-full"
      title={<span>Scene</span>}
      meta={
        <button
          type="button"
          onClick={onClose}
          aria-label="Close scene"
          title="Close the scene panel"
          className="-mr-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md hover:bg-[var(--raise)] hover:text-[var(--label)]"
          style={{ color: 'var(--label-2)' }}
        >
          <X aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
        </button>
      }
    >
      <p className="m-0 p-4 text-[1rem] leading-[1.65] [overflow-wrap:anywhere] select-text" style={{ color: 'var(--label)' }}>
        {say}
      </p>
    </Panel>
  )
}

interface BoundaryProps {
  fallback: ReactNode
  /** A new step may draw fine again. */
  resetKey: string
  children: ReactNode
}

class RenderBoundary extends Component<BoundaryProps, { failed: boolean; key: string }> {
  state = { failed: false, key: this.props.resetKey }
  static getDerivedStateFromError() {
    return { failed: true }
  }
  static getDerivedStateFromProps(props: BoundaryProps, state: { failed: boolean; key: string }) {
    return props.resetKey !== state.key ? { failed: false, key: props.resetKey } : null
  }
  render() {
    return this.state.failed ? this.props.fallback : this.props.children
  }
}

interface SceneStackProps {
  walkthrough: WalkthroughData
  onClose: () => void
  /** Header name for a code pane whose object has no language. */
  codeName?: string
  renderers?: PrimitiveRenderers
}

/**
 * The content panel of a scene: one component per visible primitive, from the registry. An
 * unknown primitive or a failing render shows the step's text, so the session carries on.
 */
export function SceneStack({ walkthrough, onClose, codeName = 'walkthrough', renderers = PRIMITIVE_RENDERERS }: SceneStackProps) {
  const { step } = walkthrough
  const entries = panelObjects(walkthrough.objects, step?.state ?? null, renderers)
  const say = step?.say ?? ''
  const index = step?.index ?? 0

  // The scene's content is on screen: the first visual after it arrived, and the step's cue.
  useEffect(() => {
    if (entries.length > 0) sceneMetrics.firstVisual()
  })
  useEffect(() => {
    if (step) sceneMetrics.cueApplied(step.index)
  }, [step])

  return (
    <div className="scene-stack">
      {entries.map(({ object, current, renderer }, position) => {
        const fallback = <Fallback say={say} onClose={onClose} />
        // Unknown primitives share one fallback: the step's text is the same for all of them.
        if (!renderer) return entries.findIndex((e) => !e.renderer) === position ? <div key="unknown" className="contents">{fallback}</div> : null
        const Draw = renderer.Component
        return (
          <RenderBoundary key={object.id} resetKey={`${index}`} fallback={fallback}>
            <Draw object={object} state={current} say={say} siblings={entries.length} name={codeName} onClose={onClose} />
          </RenderBoundary>
        )
      })}
    </div>
  )
}
