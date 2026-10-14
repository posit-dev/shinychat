import { expect, it, vi } from "vitest"
import { createSuggestionRender } from "../../src/chat/tiptap/suggestionRender"

it("keeps Escape used by the slash palette from reaching the chat or a modal", () => {
  const palette = createSuggestionRender({ paletteId: "test-palette" })
  const parent = document.createElement("div")
  const editor = document.createElement("div")
  parent.append(editor)
  const parentKeydown = vi.fn()
  parent.addEventListener("keydown", parentKeydown)
  editor.addEventListener("keydown", (event) => {
    expect(palette.onKeyDown({ event })).toBe(true)
  })

  const escape = new KeyboardEvent("keydown", {
    key: "Escape",
    bubbles: true,
    cancelable: true,
  })
  editor.dispatchEvent(escape)

  expect(escape.defaultPrevented).toBe(true)
  expect(parentKeydown).not.toHaveBeenCalled()
})
