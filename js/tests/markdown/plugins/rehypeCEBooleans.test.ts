import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeCEBooleans } from "../../../src/markdown/plugins/rehypeCEBooleans"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeCEBooleans)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeCEBooleans", () => {
  it('converts empty-string attribute on custom element to boolean (no ="")', () => {
    const md = "<my-element expanded></my-element>"
    const html = process(md)
    expect(html).toContain("<my-element")
    // Should not have expanded="" (empty string)
    expect(html).not.toContain('expanded=""')
  })

  it("leaves non-empty string attribute on custom element unchanged", () => {
    const md = '<my-element label="hello"></my-element>'
    const html = process(md)
    expect(html).toContain('label="hello"')
  })

  it("does not modify empty-string attribute on a regular HTML element", () => {
    const md = '<div class=""></div>'
    const html = process(md)
    // Regular HTML elements should not be transformed
    expect(html).toContain("<div")
    // The plugin should only touch custom elements (containing a hyphen)
    // For regular elements the attribute is left as-is
    expect(html).not.toContain("<my-")
  })
})
