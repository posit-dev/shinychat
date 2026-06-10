import React from "react"

interface CommandChipProps {
  name: string
}

export function CommandChip({ name }: CommandChipProps): React.JSX.Element {
  return (
    <span className="command-chip">
      <span className="command-chip-sigil" aria-hidden="true">/</span>
      {name}
    </span>
  )
}
