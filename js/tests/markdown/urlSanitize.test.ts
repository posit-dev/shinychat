import { describe, it, expect } from "vitest"
import type { Root, Element, Properties } from "hast"
import { sanitizeUrls } from "../../src/markdown/urlSanitize"

function makeTree(tagName: string, properties: Properties): Root {
  const element: Element = {
    type: "element",
    tagName,
    properties,
    children: [],
  }
  return { type: "root", children: [element] }
}

describe("sanitizeUrls", () => {
  it("blanks javascript: href on <a>", () => {
    const tree = makeTree("a", { href: "javascript:alert(1)" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("")
  })

  it("blanks data: href on <a>", () => {
    const tree = makeTree("a", { href: "data:text/html,<h1>hi</h1>" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("")
  })

  it("blanks vbscript: href on <a>", () => {
    const tree = makeTree("a", { href: "vbscript:MsgBox" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("")
  })

  it("allows https: href on <a>", () => {
    const tree = makeTree("a", { href: "https://example.com" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe(
      "https://example.com",
    )
  })

  it("allows http: href on <a>", () => {
    const tree = makeTree("a", { href: "http://example.com" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe(
      "http://example.com",
    )
  })

  it("allows mailto: href on <a>", () => {
    const tree = makeTree("a", { href: "mailto:x@y.com" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("mailto:x@y.com")
  })

  it("allows relative paths on <a>", () => {
    const tree = makeTree("a", { href: "/foo/bar" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("/foo/bar")
  })

  it("allows fragment-only href on <a>", () => {
    const tree = makeTree("a", { href: "#section" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe("#section")
  })

  it("blanks javascript: src on <img>", () => {
    const tree = makeTree("img", { src: "javascript:alert(1)" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.src).toBe("")
  })

  it("blanks javascript: action on <form>", () => {
    const tree = makeTree("form", { action: "javascript:alert(1)" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.action).toBe("")
  })

  it("ignores src on elements not in the src scope (e.g. <p>)", () => {
    const tree = makeTree("p", { src: "javascript:alert(1)" })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.src).toBe(
      "javascript:alert(1)",
    )
  })

  it("ignores non-string attribute values", () => {
    const tree = makeTree("a", { href: 123 })
    sanitizeUrls(tree)
    expect((tree.children[0] as Element).properties.href).toBe(123)
  })
})
