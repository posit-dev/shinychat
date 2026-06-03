import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeUnwrapBlockCEs } from "../../../src/markdown/plugins/rehypeUnwrapBlockCEs"
import { rehypeGroupWebActivity } from "../../../src/markdown/plugins/rehypeGroupWebActivity"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeUnwrapBlockCEs)
      .use(rehypeGroupWebActivity)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeGroupWebActivity", () => {
  it("wraps a consecutive run (across blank lines) into one shiny-web-activity", () => {
    const md = [
      '<shiny-web-search query="a"></shiny-web-search>',
      "",
      '<shiny-web-search-results sources="[]"></shiny-web-search-results>',
      "",
      '<shiny-web-fetch url="https://x.com" status="success"></shiny-web-fetch>',
    ].join("\n")
    const html = process(md)
    expect(html.match(/<shiny-web-activity>/g)).toHaveLength(1)
    expect(html).toMatch(
      /<shiny-web-activity>.*shiny-web-search.*shiny-web-search-results.*shiny-web-fetch.*<\/shiny-web-activity>/s,
    )
  })

  it("splits into two groups when prose interrupts the run", () => {
    const md = [
      '<shiny-web-search query="a"></shiny-web-search>',
      "",
      "Some prose in between.",
      "",
      '<shiny-web-search query="b"></shiny-web-search>',
    ].join("\n")
    const html = process(md)
    expect(html.match(/<shiny-web-activity>/g)).toHaveLength(2)
    expect(html).toContain("Some prose in between.")
  })

  it("wraps a single web element (run of length 1) without swallowing siblings", () => {
    const md = [
      '<shiny-web-search query="a"></shiny-web-search>',
      "",
      "Following prose.",
    ].join("\n")
    const html = process(md)
    expect(html.match(/<shiny-web-activity>/g)).toHaveLength(1)
    expect(html).toMatch(
      /<shiny-web-activity><shiny-web-search[^>]*><\/shiny-web-search><\/shiny-web-activity>/,
    )
    expect(html).toContain("Following prose.")
  })

  it("ends a run at a non-web custom element between web elements", () => {
    const md = [
      '<shiny-web-search query="a"></shiny-web-search>',
      "",
      '<shiny-tool-request request-id="r1" tool-name="foo" arguments="{}"></shiny-tool-request>',
      "",
      '<shiny-web-search query="b"></shiny-web-search>',
    ].join("\n")
    const html = process(md)
    expect(html.match(/<shiny-web-activity>/g)).toHaveLength(2)
    expect(html).toContain("<shiny-tool-request")
  })

  it("leaves content with no web elements untouched", () => {
    const html = process("Just a paragraph.")
    expect(html).not.toContain("shiny-web-activity")
    expect(html).toContain("Just a paragraph.")
  })
})
