import { describe, it, expect } from "vitest"
import {
  paletteOwnsEnter,
  slashPaletteAllowed,
} from "../../src/chat/tiptap/slashSuggestion"
import type { SlashCommandDef } from "../../src/transport/types"

const help: SlashCommandDef = {
  name: "help",
  description: "Show help",
  echo: false,
}
const create: SlashCommandDef = {
  name: "new",
  description: "Start again",
  echo: false,
}

describe("slashPaletteAllowed", () => {
  it("is false in a chat with no commands", () => {
    expect(slashPaletteAllowed(0, [])).toBe(false)
  })

  it("is true at the start of the input when there are commands", () => {
    expect(slashPaletteAllowed(0, [help])).toBe(true)
  })

  it("is false away from the start of the input", () => {
    expect(slashPaletteAllowed(3, [help])).toBe(false)
  })
})

describe("paletteOwnsEnter", () => {
  it("is false when there is no suggestion state", () => {
    expect(paletteOwnsEnter(undefined, [help])).toBe(false)
    expect(paletteOwnsEnter(null, [help])).toBe(false)
  })

  it("is false when the suggestion is not active", () => {
    expect(paletteOwnsEnter({ active: false }, [help])).toBe(false)
  })

  it("is true while the menu lists a command", () => {
    expect(paletteOwnsEnter({ active: true }, [help, create])).toBe(true)
  })

  it("is false when the menu lists nothing", () => {
    expect(paletteOwnsEnter({ active: true }, [])).toBe(false)
  })
})
