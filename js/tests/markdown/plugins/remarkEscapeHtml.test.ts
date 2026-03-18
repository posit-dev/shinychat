import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeStringify from "rehype-stringify"
import { remarkEscapeHtml } from "../../../src/markdown/plugins/remarkEscapeHtml"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkEscapeHtml)
      .use(remarkRehype)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("remarkEscapeHtml", () => {
  it("escapes block HTML to literal text", () => {
    const md = "<div>foo</div>"
    const html = process(md)
    // rehype-stringify encodes < as &#x3C;
    expect(html).toContain("&#x3C;div>")
    expect(html).not.toContain("<div>")
  })

  it("escapes inline HTML to literal text", () => {
    const md = "Hello <b>bold</b> world"
    const html = process(md)
    // rehype-stringify encodes < as &#x3C;
    expect(html).toContain("&#x3C;b>")
    expect(html).not.toContain("<b>")
  })

  it("still renders normal markdown (bold) as <strong>", () => {
    const md = "**bold**"
    const html = process(md)
    expect(html).toContain("<strong>bold</strong>")
  })

  it("escapes consecutive HTML nodes without skipping any", () => {
    // Each tag on its own line produces separate mdast html nodes
    const md = "<b>one</b>\n<i>two</i>\n<u>three</u>"
    const html = process(md)
    expect(html).toContain("&#x3C;b>")
    expect(html).toContain("&#x3C;i>")
    expect(html).toContain("&#x3C;u>")
  })
})
