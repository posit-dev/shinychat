import rehypeStringify from "rehype-stringify"
import { unified } from "unified"
import { describe, expect, it } from "vitest"

import { parseHtml } from "../../src/markdown/markdownToReact"
import { htmlProcessor, markdownProcessor } from "../../src/markdown/processors"

function renderMarkdown(markdown: string): string {
  const tree = markdownProcessor.runSync(markdownProcessor.parse(markdown))
  return String(
    unified()
      .use(rehypeStringify, { allowDangerousHtml: true })
      .stringify(tree),
  )
}

function aside(groundedSpan?: string): string {
  const grounding = groundedSpan ? ` grounded-span="${groundedSpan}"` : ""
  return `<shiny-aside label="Example"${grounding}>Details</shiny-aside>`
}

describe("aside processor integration", () => {
  it("grounds an aside after a blank line in Markdown", () => {
    const html = renderMarkdown(
      ["A supported claim.", "", aside("supported claim")].join("\n"),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain(
      '<span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">supported claim</span>',
    )
    expect(html).toContain('data-grounding-id="aside-grounding-1"')
  })

  it("grounds a direct raw HTML aside against the previous paragraph", () => {
    const html = String(
      unified()
        .use(rehypeStringify, { allowDangerousHtml: true })
        .stringify(
          parseHtml(
            `<p>A supported claim.</p>${aside("supported claim")}`,
            htmlProcessor,
          ),
        ),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain(
      '<span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">supported claim</span>',
    )
  })

  it("numbers an anonymous aside after automatic attachment", () => {
    const html = renderMarkdown(
      ["A claim.", "", "<shiny-aside>Details</shiny-aside>"].join("\n"),
    )

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain('<shiny-aside index="1">Details</shiny-aside>')
    expect(html).toContain("<shiny-aside-group")
  })
})
