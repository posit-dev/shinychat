import { describe, it, expect } from "vitest"
import { hideTrailingPartialSidenoteTag } from "../../src/markdown/hideTrailingPartialTag"

describe("hideTrailingPartialSidenoteTag", () => {
  it("removes a trailing partial tag name", () => {
    expect(hideTrailingPartialSidenoteTag("Hub motors<shiny-side")).toBe(
      "Hub motors",
    )
  })
  it("removes a trailing partial opening tag with attributes and no >", () => {
    expect(
      hideTrailingPartialSidenoteTag('Hub<shiny-sidenote label="eBi'),
    ).toBe("Hub")
  })
  it("removes a lone trailing <", () => {
    expect(hideTrailingPartialSidenoteTag("Hub motors <")).toBe("Hub motors ")
  })
  it("keeps a completed sidenote tag", () => {
    const s = 'Hub<shiny-sidenote label="x">note'
    expect(hideTrailingPartialSidenoteTag(s)).toBe(s)
  })
  it("keeps prose that is not a partial tag", () => {
    expect(hideTrailingPartialSidenoteTag("5 < 10 apples")).toBe(
      "5 < 10 apples",
    )
    expect(hideTrailingPartialSidenoteTag("done.")).toBe("done.")
  })
  it("only trims the trailing partial, leaving earlier complete tags", () => {
    const s = "a<shiny-sidenote>x</shiny-sidenote> and <shiny-side"
    expect(hideTrailingPartialSidenoteTag(s)).toBe(
      "a<shiny-sidenote>x</shiny-sidenote> and ",
    )
  })
})
