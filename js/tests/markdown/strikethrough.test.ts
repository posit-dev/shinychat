import { describe, it, expect } from "vitest"
import type { Element, Root } from "hast"

import { parseMarkdown } from "../../src/markdown/markdownToReact"
import {
  markdownProcessor,
  userMarkdownProcessor,
} from "../../src/markdown/processors"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Find the first <del> element in a HAST tree, or null if none. */
function findDel(node: Root | Element): Element | null {
  if (node.type === "element" && node.tagName === "del") {
    return node
  }
  if ("children" in node) {
    for (const child of node.children) {
      if (child.type === "element") {
        const found = findDel(child)
        if (found) return found
      }
    }
  }
  return null
}

/** Collect all text content from a HAST tree (recursive). */
function textContent(node: Root | Element): string {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  function collect(n: any): string {
    if (n.type === "text") return n.value as string
    if (n.children) return n.children.map(collect).join("")
    return ""
  }
  return collect(node)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("strikethrough requires two tildes", () => {
  describe("markdownProcessor (assistant content)", () => {
    it("does not render single-tilde as strikethrough", () => {
      const hast = parseMarkdown("~text~", markdownProcessor)
      expect(findDel(hast)).toBeNull()
      expect(textContent(hast)).toContain("~text~")
    })

    it("renders double-tilde as <del>", () => {
      const hast = parseMarkdown("~~text~~", markdownProcessor)
      const del = findDel(hast)
      expect(del).not.toBeNull()
      expect(textContent(del!)).toBe("text")
    })

    it("preserves tildes in approximation context (~$1.50)", () => {
      const hast = parseMarkdown(
        "first thing (~$1.50) and second thing (~$10)",
        markdownProcessor,
      )
      expect(findDel(hast)).toBeNull()
      expect(textContent(hast)).toContain("~$1.50")
      expect(textContent(hast)).toContain("~$10")
    })

    it("preserves tildes in Unix paths (~/Documents)", () => {
      const hast = parseMarkdown(
        "see ~/Documents for details",
        markdownProcessor,
      )
      expect(findDel(hast)).toBeNull()
      expect(textContent(hast)).toContain("~/Documents")
    })
  })

  describe("userMarkdownProcessor (user content)", () => {
    it("does not render single-tilde as strikethrough", () => {
      const hast = parseMarkdown("~text~", userMarkdownProcessor)
      expect(findDel(hast)).toBeNull()
      expect(textContent(hast)).toContain("~text~")
    })

    it("renders double-tilde as <del>", () => {
      const hast = parseMarkdown("~~text~~", userMarkdownProcessor)
      const del = findDel(hast)
      expect(del).not.toBeNull()
      expect(textContent(del!)).toBe("text")
    })

    it("preserves tildes in approximation context (~$1.50)", () => {
      const hast = parseMarkdown(
        "first thing (~$1.50) and second thing (~$10)",
        userMarkdownProcessor,
      )
      expect(findDel(hast)).toBeNull()
      expect(textContent(hast)).toContain("~$1.50")
      expect(textContent(hast)).toContain("~$10")
    })
  })
})
