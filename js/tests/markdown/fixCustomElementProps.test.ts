import { describe, it, expect } from "vitest"
import { fixCustomElementProps } from "../../src/markdown/markdownToReact"

describe("fixCustomElementProps", () => {
  it("returns props unchanged for standard HTML elements", () => {
    const props = { className: "foo", htmlFor: "bar" }
    const result = fixCustomElementProps("div", props)
    expect(result).toBe(props) // same reference, no copy
  })

  it("converts className to class for custom elements", () => {
    const props = { className: "foo", id: "x" }
    const result = fixCustomElementProps("my-element", props)
    expect(result).toEqual({ class: "foo", id: "x" })
    expect(result).not.toHaveProperty("className")
  })

  it("converts htmlFor to for for custom elements", () => {
    const props = { htmlFor: "input-1" }
    const result = fixCustomElementProps("my-label", props)
    expect(result).toEqual({ for: "input-1" })
  })

  it("converts multiple React prop names in one call", () => {
    const props = { className: "a", htmlFor: "b", tabIndex: 0, id: "c" }
    const result = fixCustomElementProps("custom-el", props)
    expect(result).toEqual({ class: "a", for: "b", tabindex: 0, id: "c" })
  })

  it("returns same reference when no React-specific props exist on custom element", () => {
    const props = { id: "x", "data-value": "42" }
    const result = fixCustomElementProps("my-widget", props)
    expect(result).toBe(props)
  })

  it("handles empty props object", () => {
    const props = {}
    const result = fixCustomElementProps("my-widget", props)
    expect(result).toBe(props)
  })

  it("preserves data attributes untouched", () => {
    const props = { "data-foo": "bar", className: "x" }
    const result = fixCustomElementProps("my-el", props)
    expect(result).toEqual({ "data-foo": "bar", class: "x" })
  })
})
