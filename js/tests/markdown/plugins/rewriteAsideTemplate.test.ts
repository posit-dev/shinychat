import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  rehypeRewriteAsideToTemplate,
  rehypeRewriteAsideFromTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkGfm)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeRaw)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rewriteAsideTemplate round-trip", () => {
  it("keeps an inline aside inline with its text as children", () => {
    const html = process(
      'A claim<shiny-aside label="eBicycles">a **bold** note</shiny-aside>.',
    )
    expect(html).not.toContain("<template")
    expect(html).toContain(
      '<shiny-aside label="eBicycles">a <strong>bold</strong> note</shiny-aside>',
    )
    expect(html).toContain("<p>A claim<shiny-aside")
  })

  it("nests a blank-line block body as children of the still-inline aside", () => {
    const html = process(
      'See notes<shiny-aside label="Study">\n\n**Key**\n\n- a\n- b\n\n</shiny-aside>.',
    )
    expect(html).not.toContain("<template")
    const open = html.indexOf("<shiny-aside")
    const close = html.indexOf("</shiny-aside>")
    const inner = html.slice(open, close)
    expect(inner).toContain("<strong>Key</strong>")
    expect(inner).toContain("<ul>")
    expect(inner).toContain("<li>a</li>")
    expect(inner).toContain("<li>b</li>")
    expect(html).toContain("<p>See notes<shiny-aside")
  })

  it("preserves label/url/icon attributes", () => {
    const html = process(
      'X<shiny-aside label="L" url="https://e.example" icon="https://e.example/i.png">n</shiny-aside>.',
    )
    expect(html).toContain('label="L"')
    expect(html).toContain('url="https://e.example"')
    expect(html).toContain('icon="https://e.example/i.png"')
    expect(html).not.toContain("data-shiny-aside")
  })

  it("treats a self-closing aside as empty, not swallowing following text", () => {
    const html = process(
      'A claim<shiny-aside label="x" url="https://e.example"/> and more text after.',
    )
    expect(html).not.toContain("<template")
    expect(html).toContain(
      '<shiny-aside label="x" url="https://e.example"></shiny-aside>',
    )
    // The trailing prose stays in the paragraph rather than becoming the body.
    expect(html).toContain("</shiny-aside> and more text after.</p>")
  })

  it("does not mistake a slash inside a quoted attribute for the self-close", () => {
    const html = process(
      'A claim<shiny-aside url="https://e.example/path/"/> tail.',
    )
    expect(html).toContain(
      '<shiny-aside url="https://e.example/path/"></shiny-aside>',
    )
    expect(html).toContain("</shiny-aside> tail.</p>")
  })

  it("does not rewrite an aside tag written literally inside a code fence", () => {
    const html = process("```\n<shiny-aside>x</shiny-aside>\n```")
    expect(html).not.toContain("<template")
    // The literal text is escaped inside <code>, so no real element appears.
    expect(html).not.toContain("<shiny-aside")
  })
})
