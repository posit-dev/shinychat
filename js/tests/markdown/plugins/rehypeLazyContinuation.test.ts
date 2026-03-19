import { describe, it, expect } from "vitest"
import { toHtml } from "hast-util-to-html"

import { markdownProcessor } from "../../../src/markdown/processors"
import { parseMarkdown } from "../../../src/markdown/markdownToReact"

function process(md: string): string {
  return toHtml(parseMarkdown(md, markdownProcessor))
}

describe("rehypeLazyContinuation", () => {
  it("extracts lazy continuation text from the last list item (raw HTML links)", () => {
    const md = [
      '- <a class="suggestion">Option A</a>',
      '- <a class="suggestion">Option B</a>',
      "Let me know which option!",
    ].join("\n")

    const html = process(md)
    expect(html).toContain("</ul><p>Let me know which option!</p>")
    // The last <li> should NOT contain the continuation text
    expect(html).not.toContain("Option B</a>\nLet me know")
  })

  it("extracts lazy continuation text from the last list item (markdown links)", () => {
    const md = [
      "- [Option A](suggestion:A)",
      "- [Option B](suggestion:B)",
      "Let me know which option!",
    ].join("\n")

    const html = process(md)
    expect(html).toContain("</ul><p>Let me know which option!</p>")
  })

  it("handles multi-line lazy continuation", () => {
    const md = [
      "- [Option A](suggestion:A)",
      "- [Option B](suggestion:B)",
      "Let me know which option!",
      "And another line here.",
    ].join("\n")

    const html = process(md)
    expect(html).toContain("</ul><p>")
    expect(html).toContain("Let me know which option!")
    // The full continuation text should be in the <p>
    expect(html).toContain("And another line here.")
  })

  it("does NOT modify lists followed by a blank line", () => {
    const md = [
      "- [Option A](suggestion:A)",
      "- [Option B](suggestion:B)",
      "",
      "Let me know which option!",
    ].join("\n")

    const html = process(md)
    // Already correctly renders as separate <p> (parser inserts \n)
    expect(html).toContain("</ul>\n<p>Let me know which option!</p>")
    // Should not create a duplicate <p>
    const pCount = (html.match(/<p>/g) || []).length
    expect(pCount).toBe(1)
  })

  it("does NOT modify list items with only text (no element children)", () => {
    const md = ["- plain text item", "continuation text"].join("\n")

    const html = process(md)
    // Should remain in the <li>
    expect(html).toContain("<li>plain text item\ncontinuation text</li>")
  })

  it("handles ordered lists", () => {
    const md = [
      "1. [Option A](suggestion:A)",
      "2. [Option B](suggestion:B)",
      "Let me know!",
    ].join("\n")

    const html = process(md)
    expect(html).toContain("</ol><p>Let me know!</p>")
  })

  it("does not extract when the last child is an element (no trailing text)", () => {
    const md = [
      "- [Option A](suggestion:A)",
      "- [Option B](suggestion:B)",
    ].join("\n")

    const html = process(md)
    // No <p> should be created
    expect(html).not.toContain("<p>")
  })
})
