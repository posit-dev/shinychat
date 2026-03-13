import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { remarkRawHtml } from "../../../src/markdown/plugins/remarkRawHtml"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRawHtml)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("remarkRawHtml", () => {
  it("passes through {=html} code block as raw HTML (no <pre>)", () => {
    const md = '```{=html}\n<div class="custom">Hello</div>\n```'
    const html = process(md)
    expect(html).toContain('<div class="custom">Hello</div>')
    expect(html).not.toContain("<pre>")
  })

  it("leaves code block with js language in <pre><code>", () => {
    const md = "```js\nconsole.log('hi')\n```"
    const html = process(md)
    expect(html).toContain("<pre>")
    expect(html).toContain("<code")
  })

  it("leaves code block with no language in <pre><code>", () => {
    const md = "```\nsome code\n```"
    const html = process(md)
    expect(html).toContain("<pre>")
    expect(html).toContain("<code")
  })
})
