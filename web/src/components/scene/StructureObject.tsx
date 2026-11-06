import { useRef } from 'react'
import { X } from 'lucide-react'
import { Panel } from '@/components/shell/Panel'
import type { PrimitiveProps } from '@/components/scene/registry'
import { ArrayDrawing, HashTableDrawing, QueueDrawing, StackDrawing, TreeDrawing } from '@/components/scene/StructureDrawings'
import { captionOf, summaryOf, visibleStructureViews, TITLES, type StructureView } from '@/lib/sceneStructure'
import { fitScale, layoutOf, PAD, type Laid } from '@/lib/structureLayout'
import { useElementSize } from '@/lib/useElementSize'
import { usePrefersReducedMotion } from '@/lib/useReducedMotion'

/** Room around the drawing inside its scrolling viewport, in pixels. */
const VIEWPORT_PAD = 8
/** Used before the viewport is measured, and where ResizeObserver does not exist. */
const FALLBACK_SIZE = { width: 640, height: 420 }

function countOf(view: StructureView): number {
  if (view.kind === 'hashTable') return view.buckets.reduce((n, chain) => n + chain.length, 0)
  return view.kind === 'tree' ? view.nodes.length : view.items.length
}

function Drawing({ view, laid, reduced }: { view: StructureView; laid: Laid; reduced: boolean }) {
  switch (laid.kind) {
    case 'array':
      return <ArrayDrawing view={view} layout={laid.layout} reduced={reduced} />
    case 'queue':
      return <QueueDrawing view={view} layout={laid.layout} reduced={reduced} />
    case 'stack':
      return <StackDrawing view={view} layout={laid.layout} reduced={reduced} />
    case 'hashTable':
      return <HashTableDrawing view={view} layout={laid.layout} reduced={reduced} />
    case 'tree':
      return <TreeDrawing view={view} layout={laid.layout} reduced={reduced} />
  }
}

/**
 * The structure primitive: an array, stack, queue, hash table or binary search tree as SVG. The
 * server computed every state; this only draws the contents and plays what the last operation did.
 */
export function StructureObject({ object, state, siblings, onClose }: PrimitiveProps) {
  const view = visibleStructureViews([object], state ? { [object.id]: state } : null)[0]
  const viewport = useRef<HTMLDivElement | null>(null)
  const size = useElementSize(viewport, FALLBACK_SIZE)
  const reduced = usePrefersReducedMotion()
  if (!view) return null

  const room = { width: size.width - VIEWPORT_PAD * 2, height: size.height - VIEWPORT_PAD * 2 }
  const laid = layoutOf(view, room.width)
  const natural = laid.layout
  const scale = fitScale(natural, room)
  const caption = captionOf(view)
  const title = TITLES[view.kind]
  const count = countOf(view)

  return (
    <Panel
      label={siblings > 1 ? `Walkthrough structure ${view.id}` : 'Walkthrough structure'}
      testId="structure-pane"
      className="h-full"
      title={<span>{title}</span>}
      meta={
        <>
          <span className="t-mono truncate" style={{ color: 'var(--label-3)' }}>
            {view.kind === 'hashTable' ? `${view.buckets.length} buckets, ` : ''}
            {count} {view.kind === 'tree' ? (count === 1 ? 'node' : 'nodes') : count === 1 ? 'item' : 'items'}
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close structure"
            title="Close the structure panel"
            className="-mr-1.5 grid h-7 w-7 shrink-0 place-items-center rounded-md hover:bg-[var(--raise)] hover:text-[var(--label)]"
            style={{ color: 'var(--label-2)' }}
          >
            <X aria-hidden="true" className="h-4 w-4" strokeWidth={2} />
          </button>
        </>
      }
    >
      <p data-structure-caption className="structure-caption t-mono" aria-live="polite">
        {caption}
      </p>
      <div ref={viewport} data-structure-viewport className="structure-viewport">
        <svg
          role="img"
          aria-label={summaryOf(view)}
          data-structure-root
          data-scene-object={view.id}
          data-kind={view.kind}
          data-op={view.last?.op}
          data-scale={scale.toFixed(3)}
          data-motion={reduced ? 'reduced' : 'full'}
          width={Math.round(natural.width * scale)}
          height={Math.round(natural.height * scale)}
          viewBox={`0 0 ${Math.max(natural.width, PAD * 2)} ${Math.max(natural.height, PAD * 2)}`}
          className="structure-svg"
        >
          <Drawing view={view} laid={laid} reduced={reduced} />
        </svg>
      </div>
    </Panel>
  )
}
