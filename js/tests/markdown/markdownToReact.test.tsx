import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import type { Root, Element } from "hast"
import type { ComponentType } from "react"

import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import {
  assistantProcessor,
  userProcessor,
} from "../../src/markdown/processors"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSimpleRoot(): Root {
  return {
    type: "root",
    children: [
      {
        type: "element",
        tagName: "p",
        properties: {},
        children: [{ type: "text", value: "Hello world" }],
      } satisfies Element,
    ],
  }
}

// ---------------------------------------------------------------------------
// parseMarkdown
// ---------------------------------------------------------------------------

describe("parseMarkdown", () => {
  it("returns a Root node for basic markdown", () => {
    const hast = parseMarkdown("# Hello\n\nWorld", assistantProcessor)
    expect(hast.type).toBe("root")
    expect(hast.children.length).toBeGreaterThan(0)
  })

  it("returns an empty-ish Root for empty string", () => {
    const hast = parseMarkdown("", assistantProcessor)
    expect(hast.type).toBe("root")
    // May have whitespace text nodes but no meaningful elements
    const elements = hast.children.filter((c) => c.type === "element")
    expect(elements.length).toBe(0)
  })

  it("sanitizes unsafe URLs (javascript: href)", () => {
    const hast = parseMarkdown(
      "[click](javascript:alert(1))",
      assistantProcessor,
    )
    // Walk tree looking for anchor href
    function findHref(node: Root | Element): string | undefined {
      if (node.type === "element" && node.tagName === "a") {
        return node.properties?.href as string | undefined
      }
      if ("children" in node) {
        for (const child of node.children) {
          if (child.type === "element") {
            const found = findHref(child)
            if (found !== undefined) return found
          }
        }
      }
      return undefined
    }
    const href = findHref(hast)
    // After sanitization the href must be empty string, not javascript:...
    expect(href).toBe("")
  })

  it("sanitizes unsafe URLs with userProcessor too", () => {
    const hast = parseMarkdown("[click](javascript:alert(1))", userProcessor)
    function findAnchor(node: Root | Element): Element | undefined {
      if (node.type === "element" && node.tagName === "a") return node
      if ("children" in node) {
        for (const child of node.children) {
          if (child.type === "element") {
            const found = findAnchor(child)
            if (found !== undefined) return found
          }
        }
      }
      return undefined
    }
    const anchor = findAnchor(hast)
    // rehypeSanitize may strip the href entirely or sanitizeUrls may set it to "";
    // either way the javascript: URL must not survive.
    const href = anchor?.properties?.href
    expect(String(href ?? "")).not.toContain("javascript:")
  })

  it("produces element children for non-empty input", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)
    const elements = hast.children.filter((c) => c.type === "element")
    expect(elements.length).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// hastToReact
// ---------------------------------------------------------------------------

describe("hastToReact", () => {
  it("converts a simple HAST tree to a React element", () => {
    const hast = makeSimpleRoot()
    const el = hastToReact(hast, {})
    expect(el).toBeTruthy()
    const { container } = render(el)
    expect(container.textContent).toContain("Hello world")
  })

  it("applies component overrides", () => {
    const hast = makeSimpleRoot()
    const CustomP: ComponentType<Record<string, unknown>> = (props) => {
      const children = props["children"] as React.ReactNode
      return <span data-testid="custom-p">{children}</span>
    }
    const el = hastToReact(hast, {
      tagToComponentMap: { p: CustomP as ComponentType<unknown> },
    })
    const { getByTestId } = render(el)
    expect(getByTestId("custom-p")).toBeTruthy()
    expect(getByTestId("custom-p").textContent).toContain("Hello world")
  })
})

// ---------------------------------------------------------------------------
// Streaming dot
// ---------------------------------------------------------------------------

describe("streaming dot", () => {
  it("inserts a streaming dot when streaming=true", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)
    const el = hastToReact(hast, { streaming: true })
    const { container } = render(el)
    const dot = container.querySelector(".markdown-stream-dot")
    expect(dot).not.toBeNull()
  })

  it("does NOT insert a streaming dot when streaming=false", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)
    const el = hastToReact(hast, { streaming: false })
    const { container } = render(el)
    const dot = container.querySelector(".markdown-stream-dot")
    expect(dot).toBeNull()
  })

  it("does NOT insert a streaming dot when streaming is omitted", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)
    const el = hastToReact(hast, {})
    const { container } = render(el)
    const dot = container.querySelector(".markdown-stream-dot")
    expect(dot).toBeNull()
  })

  it("CRITICAL: does NOT mutate the original HAST tree when streaming=true", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)

    // Record the total child count of every node before
    function countTotalChildren(node: Root | Element): number {
      if (!("children" in node)) return 0
      return (
        node.children.length +
        node.children.reduce((sum, child) => {
          if (child.type === "element") {
            return sum + countTotalChildren(child)
          }
          return sum
        }, 0)
      )
    }

    const beforeCount = countTotalChildren(hast)
    const beforeJson = JSON.stringify(hast)

    // Render with streaming=true (should clone before inserting dot)
    hastToReact(hast, { streaming: true })

    const afterJson = JSON.stringify(hast)
    const afterCount = countTotalChildren(hast)

    expect(afterCount).toBe(beforeCount)
    expect(afterJson).toBe(beforeJson)
  })

  it("repeated streaming renders do not accumulate dots", () => {
    const hast = parseMarkdown("Hello", assistantProcessor)

    // Render streaming three times
    for (let i = 0; i < 3; i++) {
      const el = hastToReact(hast, { streaming: true })
      const { container } = render(el)
      const dots = container.querySelectorAll(".markdown-stream-dot")
      expect(dots.length).toBe(1)
    }

    // Also confirm the original HAST is still clean
    const el = hastToReact(hast, { streaming: false })
    const { container } = render(el)
    const dots = container.querySelectorAll(".markdown-stream-dot")
    expect(dots.length).toBe(0)
  })
})
