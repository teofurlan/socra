import { useEffect, useRef } from 'react'
import type { AgentCommand } from '@/types/agent'

/** The commands a half-typed "/query" offers: names that start with it first, then names containing it. */
export function matchingCommands(commands: AgentCommand[], query: string): AgentCommand[] {
  const wanted = query.toLowerCase()
  const starting: AgentCommand[] = []
  const containing: AgentCommand[] = []
  for (const command of commands) {
    const name = command.name.toLowerCase()
    if (name.startsWith(wanted)) starting.push(command)
    else if (name.includes(wanted)) containing.push(command)
  }
  return [...starting, ...containing]
}

export const COMMAND_MENU_ID = 'command-menu'
export const commandOptionId = (index: number) => `${COMMAND_MENU_ID}-option-${index}`

interface CommandMenuProps {
  commands: AgentCommand[]
  active: number
  onPick: (command: AgentCommand) => void
}

/** The list above the composer; the field keeps the focus and drives it with the keyboard. */
export function CommandMenu({ commands, active, onPick }: CommandMenuProps) {
  const activeRef = useRef<HTMLLIElement>(null)
  useEffect(() => {
    // The page may not scroll boxes in every environment (jsdom has no scrollIntoView).
    activeRef.current?.scrollIntoView?.({ block: 'nearest' })
  }, [active])

  return (
    <ul
      id={COMMAND_MENU_ID}
      role="listbox"
      aria-label="Commands"
      className="command-menu t-ui m-0 list-none p-1"
    >
      {commands.map((command, index) => (
        <li
          key={command.name}
          id={commandOptionId(index)}
          ref={index === active ? activeRef : undefined}
          role="option"
          aria-selected={index === active}
          // Keep the focus in the field: a click completes, it never moves the caret away.
          onMouseDown={(event) => {
            event.preventDefault()
            onPick(command)
          }}
          className="command-option"
        >
          <span data-command-name style={{ color: 'var(--accent)' }}>/{command.name}</span>
          {command.hint && <span style={{ color: 'var(--label-2)' }}>{command.hint}</span>}
          {command.description && (
            <span className="command-description" style={{ color: 'var(--label-2)' }}>{command.description}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
