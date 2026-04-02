import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeUnwrapBlockCEs } from "../../src/markdown/plugins/rehypeUnwrapBlockCEs"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeUnwrapBlockCEs)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeUnwrapBlockCEs", () => {
  it("unwraps a custom element from a <p> parent", () => {
    const md =
      '<shiny-tool-request request-id="r1" tool-name="foo" arguments="{}"></shiny-tool-request>'
    const html = process(md)
    // Should NOT be wrapped in <p>
    expect(html).not.toMatch(/<p>.*<shiny-tool-request/)
    // The element itself should still be present
    expect(html).toContain("<shiny-tool-request")
  })

  it("unwraps shinychat-raw-html from a <p> parent", () => {
    const md = "<shinychat-raw-html><div>hello</div></shinychat-raw-html>"
    const html = process(md)
    expect(html).not.toMatch(/<p>.*<shinychat-raw-html/)
    expect(html).toContain("<shinychat-raw-html")
  })

  it("unwraps shiny-tool-result from a <p> parent", () => {
    const md =
      '<shiny-tool-result request-id="r1" tool-name="foo" status="success" value="ok" value-type="text"></shiny-tool-result>'
    const html = process(md)
    expect(html).not.toMatch(/<p>.*<shiny-tool-result/)
    expect(html).toContain("<shiny-tool-result")
  })

  it("preserves sibling text when unwrapping", () => {
    // Text before and after the CE in the same paragraph
    const md =
      'Before <shiny-tool-request request-id="r1" tool-name="foo" arguments="{}"></shiny-tool-request> After'
    const html = process(md)
    // Text should survive, and the CE should not be inside a <p>
    expect(html).toContain("Before")
    expect(html).toContain("After")
    expect(html).toContain("<shiny-tool-request")
  })

  it("does not affect non-custom elements inside <p>", () => {
    const md = "Hello <strong>world</strong>"
    const html = process(md)
    expect(html).toMatch(/<p>.*<strong>world<\/strong>.*<\/p>/)
  })

  it("does not affect custom elements that are not block-level tool components", () => {
    const md = '<my-inline-widget foo="bar"></my-inline-widget>'
    const html = process(md)
    // Generic custom elements should remain wrapped in <p>
    expect(html).toMatch(/<p>.*<my-inline-widget/)
  })
})
