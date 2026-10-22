import React, { useEffect, useRef } from "react"
import type { SlashCommandDef } from "../transport/types"
import { submitKeyLabel, type SubmitKey } from "./tiptap/submitShortcut"

export interface SlashCommandPaletteProps {
  id: string
  // The already-filtered commands to display.
  commands: SlashCommandDef[]
  // Index into `commands` of the highlighted item, or -1 when there is none.
  effectiveIndex: number
  onSelect: (command: SlashCommandDef) => void
  onHighlight: (index: number) => void
  submitKey?: SubmitKey
}

export function filterSlashCommands(
  commands: SlashCommandDef[],
  filter: string,
): SlashCommandDef[] {
  const lower = filter.toLowerCase()
  return commands.filter((cmd) => cmd.name.toLowerCase().startsWith(lower))
}

export function SlashCommandPalette({
  id,
  commands,
  effectiveIndex,
  onSelect,
  onHighlight,
  submitKey = "enter",
}: SlashCommandPaletteProps): React.JSX.Element | null {
  const listRef = useRef<HTMLUListElement>(null)

  useEffect(() => {
    const item = listRef.current?.children[effectiveIndex] as
      | HTMLElement
      | undefined
    item?.scrollIntoView({ block: "nearest" })
  }, [effectiveIndex])

  return (
    <ul
      id={id}
      ref={listRef}
      className="shiny-chat-slash-palette"
      role="listbox"
      aria-label="Slash commands"
      onMouseDown={(e) => e.preventDefault()}
    >
      {commands.length === 0 ? (
        <li className="shiny-chat-slash-palette-empty" role="presentation">
          No matching commands. Press {submitKeyLabel(submitKey)} to send as a
          message.
        </li>
      ) : (
        commands.map((cmd, i) => (
          <li
            key={cmd.name}
            id={`${id}-item-${cmd.name}`}
            className={
              "shiny-chat-slash-palette-item" +
              (i === effectiveIndex ? " highlighted" : "")
            }
            role="option"
            aria-selected={i === effectiveIndex}
            onClick={() => onSelect(cmd)}
            onMouseEnter={() => onHighlight(i)}
          >
            <span className="shiny-chat-slash-palette-name">/{cmd.name}</span>
            <span className="shiny-chat-slash-palette-desc">
              {cmd.description}
            </span>
          </li>
        ))
      )}
    </ul>
  )
}
