import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeAccessibleSuggestions)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeAccessibleSuggestions", () => {
  it("adds keyboard and aria attributes to suggestion class nodes", () => {
    const html = process("<span class='suggestion'>Try this</span>")

    expect(html).toContain('tabindex="0"')
    expect(html).toContain('role="button"')
    expect(html).toContain('aria-label="Use chat suggestion: Try this"')
  })

  it("uses data-suggestion when present", () => {
    const html = process(
      "<div data-suggestion='Prompt text'>Visible label</div>",
    )

    expect(html).toContain('aria-label="Use chat suggestion: Prompt text"')
  })

  it("preserves existing accessibility attributes", () => {
    const html = process(
      "<button class='suggestion' tabindex='-1' role='menuitem' aria-label='Custom'>Prompt</button>",
    )

    expect(html).toContain('tabindex="-1"')
    expect(html).toContain('role="menuitem"')
    expect(html).toContain('aria-label="Custom"')
  })
})
