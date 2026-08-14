import { describe, it, expect } from "vitest"
import { hideTrailingPartialAsideTag } from "../../src/markdown/hideTrailingPartialTag"

describe("hideTrailingPartialAsideTag", () => {
  it("removes a trailing partial tag name", () => {
    expect(hideTrailingPartialAsideTag("Hub motors<shiny-asi")).toBe(
      "Hub motors",
    )
  })
  it("removes a trailing partial opening tag with attributes and no >", () => {
    expect(hideTrailingPartialAsideTag('Hub<shiny-aside label="eBi')).toBe(
      "Hub",
    )
  })
  it("removes a lone trailing <", () => {
    expect(hideTrailingPartialAsideTag("Hub motors <")).toBe("Hub motors ")
  })
  it("keeps a completed aside tag", () => {
    const s = 'Hub<shiny-aside label="x">note'
    expect(hideTrailingPartialAsideTag(s)).toBe(s)
  })
  it("keeps prose that is not a partial tag", () => {
    expect(hideTrailingPartialAsideTag("5 < 10 apples")).toBe("5 < 10 apples")
    expect(hideTrailingPartialAsideTag("done.")).toBe("done.")
  })
  it("only trims the trailing partial, leaving earlier complete tags", () => {
    const s = "a<shiny-aside>x</shiny-aside> and <shiny-asi"
    expect(hideTrailingPartialAsideTag(s)).toBe(
      "a<shiny-aside>x</shiny-aside> and ",
    )
  })
})
