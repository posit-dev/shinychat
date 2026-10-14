import { describe, it, expect } from "vitest"
import type { Element, Root } from "hast"
import { unified } from "unified"
import rehypeStringify from "rehype-stringify"
import { markdownProcessor } from "../../src/markdown/processors"

function render(md: string): string {
  const tree = markdownProcessor.runSync(markdownProcessor.parse(md))
  return String(
    unified()
      .use(rehypeStringify, { allowDangerousHtml: true })
      .stringify(tree),
  )
}

function activities(md: string): Element[] {
  const tree = markdownProcessor.runSync(markdownProcessor.parse(md)) as Root
  return tree.children.filter(
    (node): node is Element =>
      node.type === "element" && node.tagName === "shiny-web-activity",
  )
}

const cite = (url: string, title: string, groundedSpan: string) =>
  `<shiny-aside data-citation label="${new URL(url).hostname}" url="${url}" grounded-span="${groundedSpan}"><a href="${url}">${title}</a></shiny-aside>`

describe("markdownProcessor citation occurrences", () => {
  it("preserves repeated citations for separate grounded claims", () => {
    const u = "https://ebicycles.example/hub"
    const html = render(
      `First claim${cite(u, "Hub vs Mid", "First claim")} and second claim${cite(u, "Hub vs Mid", "second claim")}.`,
    )
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(2)
    expect(html).toContain('data-grounding-id="aside-grounding-1"')
    expect(html).toContain('data-grounding-id="aside-grounding-2"')
  })
})
