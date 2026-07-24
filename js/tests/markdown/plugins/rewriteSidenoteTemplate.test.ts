import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  rehypeRewriteSidenoteToTemplate,
  rehypeRewriteSidenoteFromTemplate,
} from "../../../src/markdown/plugins/rewriteSidenoteTemplate"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkGfm)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteSidenoteToTemplate)
      .use(rehypeRaw)
      .use(rehypeRewriteSidenoteFromTemplate)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rewriteSidenoteTemplate round-trip", () => {
  it("keeps an inline sidenote inline with its text as children", () => {
    const html = process(
      'A claim<shiny-sidenote label="eBicycles">a **bold** note</shiny-sidenote>.',
    )
    expect(html).not.toContain("<template")
    expect(html).toContain(
      '<shiny-sidenote label="eBicycles">a <strong>bold</strong> note</shiny-sidenote>',
    )
    expect(html).toContain("<p>A claim<shiny-sidenote")
  })

  it("nests a blank-line block body as children of the still-inline sidenote", () => {
    const html = process(
      'See notes<shiny-sidenote label="Study">\n\n**Key**\n\n- a\n- b\n\n</shiny-sidenote>.',
    )
    expect(html).not.toContain("<template")
    const open = html.indexOf("<shiny-sidenote")
    const close = html.indexOf("</shiny-sidenote>")
    const inner = html.slice(open, close)
    expect(inner).toContain("<strong>Key</strong>")
    expect(inner).toContain("<ul>")
    expect(inner).toContain("<li>a</li>")
    expect(inner).toContain("<li>b</li>")
    expect(html).toContain("<p>See notes<shiny-sidenote")
  })

  it("preserves label/url/icon attributes", () => {
    const html = process(
      'X<shiny-sidenote label="L" url="https://e.example" icon="https://e.example/i.png">n</shiny-sidenote>.',
    )
    expect(html).toContain('label="L"')
    expect(html).toContain('url="https://e.example"')
    expect(html).toContain('icon="https://e.example/i.png"')
    expect(html).not.toContain("data-shiny-sidenote")
  })

  it("does not rewrite a sidenote tag written literally inside a code fence", () => {
    const html = process("```\n<shiny-sidenote>x</shiny-sidenote>\n```")
    expect(html).not.toContain("<template")
    // The literal text is escaped inside <code>, so no real element appears.
    expect(html).not.toContain("<shiny-sidenote")
  })
})
