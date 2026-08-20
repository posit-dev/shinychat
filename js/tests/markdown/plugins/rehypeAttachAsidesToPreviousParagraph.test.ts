import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import { unified } from "unified"
import { describe, expect, it } from "vitest"

import { rehypeAttachAsidesToPreviousParagraph } from "../../../src/markdown/plugins/rehypeAttachAsidesToPreviousParagraph"
import {
  rehypeRewriteAsideFromTemplate,
  rehypeRewriteAsideToTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"

function process(source: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeRaw)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeAttachAsidesToPreviousParagraph)
      .use(rehypeStringify)
      .processSync(source),
  )
}

describe("rehypeAttachAsidesToPreviousParagraph", () => {
  it("attaches an aside-only paragraph to the previous paragraph", () => {
    const html = process(
      [
        "Supported claim.",
        "",
        '<shiny-aside label="Source">Details</shiny-aside>',
      ].join("\n"),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain(
      '<p>Supported claim.<shiny-aside label="Source">Details</shiny-aside></p>',
    )
  })

  it("attaches a direct HTML aside sibling to the previous paragraph", () => {
    const html = process(
      '<p>Supported claim.</p><shiny-aside label="Source">Details</shiny-aside>',
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain(
      '<p>Supported claim.<shiny-aside label="Source">Details</shiny-aside></p>',
    )
  })

  it("moves several asides from one standalone paragraph", () => {
    const html = process(
      [
        "<p>Supported claim.</p>",
        "<p>",
        '<shiny-aside label="A">First</shiny-aside>',
        '<shiny-aside label="B">Second</shiny-aside>',
        "</p>",
      ].join(""),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html.indexOf('label="A"')).toBeLessThan(html.indexOf('label="B"'))
  })

  it("preserves order across consecutive standalone asides", () => {
    const html = process(
      [
        "Supported claim.",
        "",
        '<shiny-aside label="A">First</shiny-aside>',
        "",
        '<shiny-aside label="B">Second</shiny-aside>',
      ].join("\n"),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html.indexOf('label="A"')).toBeLessThan(html.indexOf('label="B"'))
  })

  it("attaches an aside-only paragraph inside the same list item", () => {
    const html = process(
      '<ul><li><p>Supported claim.</p><p><shiny-aside label="Source">Details</shiny-aside></p></li></ul>',
    )

    expect(html).toContain(
      '<li><p>Supported claim.<shiny-aside label="Source">Details</shiny-aside></p></li>',
    )
  })

  it("attaches a direct aside after a list-item paragraph", () => {
    const html = process(
      '<ul><li><p>Supported claim.</p><shiny-aside label="Source"><p><strong>Reason</strong></p></shiny-aside></li></ul>',
    )

    expect(html).toContain(
      '<p>Supported claim.<shiny-aside label="Source"><p><strong>Reason</strong></p></shiny-aside></p>',
    )
    expect(html).toContain("<strong>Reason</strong>")
  })

  it.each([
    ["code", "<pre><code>value</code></pre>"],
    ["list", "<ul><li>Item</li></ul>"],
    ["table", "<table><tbody><tr><td>Value</td></tr></tbody></table>"],
    ["heading", "<h2>Heading</h2>"],
    ["quotation", "<blockquote><p>Quote</p></blockquote>"],
  ])("does not reach across a %s block", (_name, block) => {
    const html = process(
      `${block}<p><shiny-aside label="Source">Details</shiny-aside></p>`,
    )

    expect(html).toContain(
      `${block}<p><shiny-aside label="Source">Details</shiny-aside></p>`,
    )
  })

  it("leaves a paragraph with non-aside content in place", () => {
    const html = process(
      '<p>Claim.</p><p>Note: <shiny-aside label="Source">Details</shiny-aside></p>',
    )

    expect(html).toContain(
      '<p>Claim.</p><p>Note: <shiny-aside label="Source">Details</shiny-aside></p>',
    )
  })

  it("does not attach an aside across list-item boundaries", () => {
    const html = process(
      '<ul><li><p>First item.</p></li><li><p><shiny-aside label="Source">Details</shiny-aside></p></li></ul>',
    )

    expect(html).toContain(
      '<li><p>First item.</p></li><li><p><shiny-aside label="Source">Details</shiny-aside></p></li>',
    )
  })
})
