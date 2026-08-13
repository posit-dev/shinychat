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

  it("attaches fallback citations to their preceding activity burst", () => {
    const firstUrl = "https://first.example/source"
    const secondUrl = "https://second.example/source"
    const sourceActivities = activities(
      [
        '<shiny-web-search query="first query"></shiny-web-search>',
        `First answer${cite(firstUrl, "First source", "First answer")}.`,
        '<shiny-web-search query="second query"></shiny-web-search>',
        `Second answer${cite(secondUrl, "Second source", "Second answer")}.`,
      ].join("\n\n"),
    )

    expect(sourceActivities).toHaveLength(2)
    expect(sourceActivities[0]!.properties.citedSources).toBe(
      JSON.stringify([{ url: firstUrl, title: "First source" }]),
    )
    expect(sourceActivities[1]!.properties.citedSources).toBe(
      JSON.stringify([{ url: secondUrl, title: "Second source" }]),
    )
  })
})
