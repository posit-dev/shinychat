import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeStringify from "rehype-stringify"
import { rehypeExternalLinks } from "../../../src/markdown/plugins/rehypeExternalLinks"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype)
      .use(rehypeExternalLinks)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeExternalLinks", () => {
  it("adds target, rel, and data-shinychat-link to https:// links", () => {
    const md = "[example](https://example.com)"
    const html = process(md)
    expect(html).toContain('target="_blank"')
    expect(html).toContain("noopener")
    expect(html).toContain("noreferrer")
    expect(html).toContain("data-shinychat-link")
  })

  it("adds target, rel, and data-shinychat-link to http:// links", () => {
    const md = "[example](http://example.com)"
    const html = process(md)
    expect(html).toContain('target="_blank"')
    expect(html).toContain("noopener")
    expect(html).toContain("noreferrer")
    expect(html).toContain("data-shinychat-link")
  })

  it("adds target, rel, and data-shinychat-link to protocol-relative // links", () => {
    const md = "[example](//example.com)"
    const html = process(md)
    expect(html).toContain('target="_blank"')
    expect(html).toContain("noopener")
    expect(html).toContain("noreferrer")
    expect(html).toContain("data-shinychat-link")
  })

  it("marks relative URLs for interception", () => {
    const md = "[page](about/page)"
    const html = process(md)
    expect(html).toContain('target="_blank"')
    expect(html).toContain("noopener")
    expect(html).toContain("noreferrer")
    expect(html).toContain("data-shinychat-link")
  })

  it("does not modify fragment-only hrefs", () => {
    const md = "[section](#section-id)"
    const html = process(md)
    expect(html).not.toContain('target="_blank"')
    expect(html).not.toContain("data-shinychat-link")
  })

  it("does not modify non-http scheme links", () => {
    const md = "[email](mailto:user@example.com)"
    const html = process(md)
    expect(html).not.toContain('target="_blank"')
    expect(html).not.toContain("data-shinychat-link")
  })
})
