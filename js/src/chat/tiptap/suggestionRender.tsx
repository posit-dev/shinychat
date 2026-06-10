import React from "react"
import { createRoot, type Root } from "react-dom/client"
import {
  SlashCommandPalette,
  filterSlashCommands,
} from "../SlashCommandPalette"
import type { SlashCommandDef } from "../../transport/types"

interface SuggestionRenderProps {
  paletteId: string
  commands: SlashCommandDef[]
}

interface SuggestionCallbackProps {
  query: string
  clientRect?: (() => DOMRect | null) | null
  command: (props: { name: string }) => void
  decorationNode?: Element | null
}

export function createSuggestionRender({
  paletteId,
  commands,
}: SuggestionRenderProps) {
  let popup: HTMLDivElement | null = null
  let root: Root | null = null
  let highlightedIndex = 0
  let filteredCommands: SlashCommandDef[] = []
  let currentCommand: ((props: { name: string }) => void) | null = null

  function updatePosition(
    clientRect: (() => DOMRect | null) | null | undefined,
  ) {
    if (!popup || !clientRect) return
    const rect = clientRect()
    if (!rect) return

    const popupHeight = popup.offsetHeight
    const spaceAbove = rect.top
    const spaceBelow = window.innerHeight - rect.bottom
    const gap = 4

    popup.style.left = `${rect.left + window.scrollX}px`

    if (spaceBelow >= popupHeight + gap || spaceBelow >= spaceAbove) {
      popup.style.top = `${rect.bottom + window.scrollY + gap}px`
      popup.style.bottom = ""
    } else {
      popup.style.top = ""
      popup.style.bottom = `${window.innerHeight - rect.top - window.scrollY + gap}px`
    }
  }

  function renderPalette() {
    if (!root) return
    root.render(
      <SlashCommandPalette
        id={paletteId}
        commands={filteredCommands}
        effectiveIndex={
          highlightedIndex >= 0
            ? Math.min(highlightedIndex, filteredCommands.length - 1)
            : -1
        }
        onSelect={(cmd) => {
          currentCommand?.({ name: cmd.name })
        }}
        onHighlight={(index) => {
          highlightedIndex = index
          renderPalette()
        }}
      />,
    )
  }

  let onResizeScroll: (() => void) | null = null
  let outsideClickHandler: ((e: PointerEvent) => void) | null = null

  function cleanup() {
    if (onResizeScroll) {
      window.removeEventListener("resize", onResizeScroll)
      window.removeEventListener("scroll", onResizeScroll, true)
      onResizeScroll = null
    }
    if (outsideClickHandler) {
      document.removeEventListener("pointerdown", outsideClickHandler, true)
      outsideClickHandler = null
    }
    if (root) {
      root.unmount()
      root = null
    }
    if (popup) {
      popup.remove()
      popup = null
    }
    currentCommand = null
  }

  return {
    onStart(props: SuggestionCallbackProps) {
      filteredCommands = filterSlashCommands(commands, props.query)
      highlightedIndex = 0
      currentCommand = props.command

      popup = document.createElement("div")
      popup.style.position = "fixed"
      popup.style.zIndex = "var(--slash-palette-z-index, 1050)"
      popup.style.width = "max-content"
      popup.style.maxWidth = "400px"
      document.body.appendChild(popup)

      root = createRoot(popup)
      renderPalette()

      requestAnimationFrame(() => updatePosition(props.clientRect))

      onResizeScroll = () => updatePosition(props.clientRect)
      window.addEventListener("resize", onResizeScroll)
      window.addEventListener("scroll", onResizeScroll, true)

      outsideClickHandler = (e: PointerEvent) => {
        if (popup && !popup.contains(e.target as Node)) {
          // The suggestion plugin handles dismiss; we just need to not interfere
        }
      }
      document.addEventListener("pointerdown", outsideClickHandler, true)
    },

    onUpdate(props: SuggestionCallbackProps) {
      filteredCommands = filterSlashCommands(commands, props.query)
      highlightedIndex = 0
      currentCommand = props.command
      renderPalette()
      requestAnimationFrame(() => updatePosition(props.clientRect))
    },

    onKeyDown({ event }: { event: KeyboardEvent }): boolean {
      if (event.key === "ArrowDown") {
        highlightedIndex =
          filteredCommands.length === 0
            ? 0
            : (highlightedIndex + 1) % filteredCommands.length
        renderPalette()
        return true
      }
      if (event.key === "ArrowUp") {
        highlightedIndex =
          filteredCommands.length === 0
            ? 0
            : (highlightedIndex - 1 + filteredCommands.length) %
              filteredCommands.length
        renderPalette()
        return true
      }
      if (event.key === "Enter" || event.key === "Tab") {
        if (filteredCommands.length > 0 && highlightedIndex >= 0) {
          const selected =
            filteredCommands[
              Math.min(highlightedIndex, filteredCommands.length - 1)
            ]
          if (selected) {
            currentCommand?.({ name: selected.name })
          }
        }
        return true
      }
      if (event.key === "Escape") {
        return true
      }
      return false
    },

    onExit() {
      cleanup()
    },
  }
}
