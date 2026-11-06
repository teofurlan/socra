import { CodePane } from '@/components/CodePane'
import type { PrimitiveProps } from '@/components/scene/registry'
import { visibleCodeViews } from '@/lib/scene'

/** The code primitive: a CodePane with the step's line focus. */
export function CodeObject({ object, state, siblings, name, onClose }: PrimitiveProps) {
  const view = visibleCodeViews([object], state ? { [object.id]: state } : null)[0]
  if (!view) return null
  return (
    <CodePane
      code={view.code}
      name={view.language || name}
      lang={view.language}
      focus={view.focus}
      sceneObject={view.id}
      label={siblings > 1 ? `Walkthrough code ${view.id}` : 'Walkthrough code'}
      onClose={onClose}
    />
  )
}
