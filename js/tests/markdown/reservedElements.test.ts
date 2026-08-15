import { describe, it, expect } from "vitest"
import {
  RESERVED_ELEMENTS,
  escapeReservedElements,
} from "../../src/markdown/reservedElements"

describe("escapeReservedElements", () => {
  it("escapes every reserved element name", () => {
    for (const name of RESERVED_ELEMENTS) {
      expect(escapeReservedElements(`<${name}>`)).toBe(`&lt;${name}>`)
      expect(escapeReservedElements(`</${name}>`)).toBe(`&lt;/${name}>`)
    }
  })

  it("escapes regardless of case, since parse5 lowercases tag names", () => {
    expect(escapeReservedElements("<SHINYCHAT-RAW-HTML>")).toBe(
      "&lt;SHINYCHAT-RAW-HTML>",
    )
    expect(escapeReservedElements("<Shiny-Tool-Result>")).toBe(
      "&lt;Shiny-Tool-Result>",
    )
  })

  it("escapes tags carrying attributes", () => {
    expect(
      escapeReservedElements(`<shiny-tool-result icon="<img onerror=x>">`),
    ).toBe(`&lt;shiny-tool-result icon="<img onerror=x>">`)
  })

  it("escapes a tag with a newline before its attributes", () => {
    expect(escapeReservedElements("<shiny-tool-request\nfoo>")).toBe(
      "&lt;shiny-tool-request\nfoo>",
    )
  })

  it("escapes a self-closing form", () => {
    expect(escapeReservedElements("<shinychat-raw-html/>")).toBe(
      "&lt;shinychat-raw-html/>",
    )
  })

  it("escapes a bare name at end of input", () => {
    expect(escapeReservedElements("<shinychat-raw-html")).toBe(
      "&lt;shinychat-raw-html",
    )
  })

  it("escapes every occurrence, not just the first", () => {
    const input = "<shinychat-raw-html>a</shinychat-raw-html>"
    expect(escapeReservedElements(input)).toBe(
      "&lt;shinychat-raw-html>a&lt;/shinychat-raw-html>",
    )
  })

  it("leaves names that merely start with a reserved name alone", () => {
    expect(escapeReservedElements("<shinychat-raw-htmlx>")).toBe(
      "<shinychat-raw-htmlx>",
    )
    expect(escapeReservedElements("<shiny-tool-resultant>")).toBe(
      "<shiny-tool-resultant>",
    )
  })

  it("leaves unrelated markup alone", () => {
    const input =
      "# Title\n\n<div class='x'>hi</div>\n\n<shiny-tool>no</shiny-tool>"
    expect(escapeReservedElements(input)).toBe(input)
  })

  it("returns content unchanged when there is nothing to escape", () => {
    const input = "just some **markdown**"
    expect(escapeReservedElements(input)).toBe(input)
  })
})
