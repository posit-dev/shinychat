import { describe, it, expect } from "vitest"
import type { Root, Element, Text } from "hast"
import {
  insertStreamingDot,
  withStreamingDot,
} from "../../src/markdown/streamingDot"

function makeRoot(...children: Root["children"]): Root {
  return { type: "root", children }
}

function el(tagName: string, children: Element["children"] = []): Element {
  return { type: "element", tagName, properties: {}, children }
}

function text(value: string): Text {
  return { type: "text", value }
}

function findDot(node: Root | Element): Element | undefined {
  for (const child of node.children) {
    if (
      child.type === "element" &&
      child.tagName === "svg" &&
      (child.properties.className as string[])?.includes("markdown-stream-dot")
    ) {
      return child
    }
    if (child.type === "element") {
      const found = findDot(child)
      if (found) return found
    }
  }
  return undefined
}

describe("insertStreamingDot", () => {
  it("does nothing on an empty tree", () => {
    const tree = makeRoot()
    insertStreamingDot(tree)
    expect(tree.children).toHaveLength(0)
  })

  it("appends dot inside a <p> that ends the tree", () => {
    const p = el("p", [text("Hello")])
    const tree = makeRoot(p)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(p.children).toContain(dot)
  })

  it("recurses into <pre> and appends dot inside <code>", () => {
    const code = el("code", [text("x = 1")])
    const pre = el("pre", [code])
    const tree = makeRoot(pre)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(code.children).toContain(dot)
  })

  it("recurses into <ul> and appends dot inside <li>", () => {
    const li = el("li", [text("item")])
    const ul = el("ul", [li])
    const tree = makeRoot(ul)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(li.children).toContain(dot)
  })

  it("appends dot at parent level for non-container elements", () => {
    const table = el("table", [el("tr", [el("td", [text("cell")])])])
    const tree = makeRoot(table)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(tree.children).toContain(dot)
  })

  it("creates an SVG dot node with correct class", () => {
    const p = el("p", [text("Hello")])
    const tree = makeRoot(p)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(dot!.tagName).toBe("svg")
    expect(dot!.properties.className).toContain("markdown-stream-dot")
  })

  it("appends dot inside <h1> (an inline container)", () => {
    const h1 = el("h1", [text("Title")])
    const tree = makeRoot(h1)
    insertStreamingDot(tree)
    const dot = findDot(tree)
    expect(dot).toBeDefined()
    expect(h1.children).toContain(dot)
  })
})

describe("withStreamingDot (immutable)", () => {
  it("does not mutate the original tree", () => {
    const p = el("p", [text("Hello")])
    const tree = makeRoot(p)
    const originalChildCount = p.children.length

    const result = withStreamingDot(tree)

    expect(p.children).toHaveLength(originalChildCount)
    expect(findDot(tree)).toBeUndefined()
    expect(findDot(result)).toBeDefined()
  })

  it("returns the same tree for empty roots", () => {
    const tree = makeRoot()
    const result = withStreamingDot(tree)
    expect(result).toBe(tree)
  })

  it("shares sibling subtrees by reference", () => {
    const sibling = el("p", [text("first paragraph")])
    const target = el("p", [text("streaming content")])
    const tree = makeRoot(sibling, target)

    const result = withStreamingDot(tree)

    // The sibling node should be the exact same object (shared, not copied)
    expect(result.children[0]).toBe(sibling)
    // The target node should be a different object (copied along the spine)
    expect(result.children[1]).not.toBe(target)
  })

  it("shares deeply nested siblings by reference", () => {
    const deepSibling = el("li", [text("first")])
    const deepTarget = el("li", [text("streaming")])
    const ul = el("ul", [deepSibling, deepTarget])
    const unrelatedP = el("p", [text("unrelated")])
    const tree = makeRoot(unrelatedP, ul)

    const result = withStreamingDot(tree)

    // Unrelated sibling at root level is shared
    expect(result.children[0]).toBe(unrelatedP)
    // The ul is on the spine, so it's copied
    const resultUl = result.children[1] as Element
    expect(resultUl).not.toBe(ul)
    // First li inside ul is a sibling of the target, so it's shared
    expect(resultUl.children[0]).toBe(deepSibling)
    // Target li is on the spine, so it's copied
    expect(resultUl.children[1]).not.toBe(deepTarget)
    // Dot is in the copied target
    expect(findDot(result)).toBeDefined()
  })

  it("inserts dot in the same location as insertStreamingDot", () => {
    const cases = [
      // Simple paragraph
      () => makeRoot(el("p", [text("Hello")])),
      // Nested pre > code
      () => makeRoot(el("pre", [el("code", [text("x = 1")])])),
      // List
      () => makeRoot(el("ul", [el("li", [text("item")])])),
      // Non-container (dot at root level)
      () => makeRoot(el("table", [el("tr", [el("td", [text("cell")])])])),
      // Heading
      () => makeRoot(el("h1", [text("Title")])),
    ]

    for (const makeTree of cases) {
      const mutableTree = makeTree()
      insertStreamingDot(mutableTree)
      const mutableDotParent = findDotParent(mutableTree)

      const immutableResult = withStreamingDot(makeTree())
      const immutableDotParent = findDotParent(immutableResult)

      // Both approaches should insert the dot in an element with the same tag
      expect(immutableDotParent?.type).toBe(mutableDotParent?.type)
      if (mutableDotParent?.type === "element") {
        expect((immutableDotParent as Element).tagName).toBe(
          mutableDotParent.tagName,
        )
      }
    }
  })
})

/** Find the parent node that directly contains the streaming dot. */
function findDotParent(node: Root | Element): Root | Element | undefined {
  for (const child of node.children) {
    if (
      child.type === "element" &&
      child.tagName === "svg" &&
      (child.properties.className as string[])?.includes("markdown-stream-dot")
    ) {
      return node
    }
    if (child.type === "element") {
      const found = findDotParent(child)
      if (found) return found
    }
  }
  return undefined
}
