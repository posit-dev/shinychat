import { describe, it, expect } from "vitest"
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

const cite = (url: string, title: string) =>
  `<shiny-aside data-citation label="${new URL(url).hostname}" url="${url}"><a href="${url}">${title}</a></shiny-aside>`

describe("markdownProcessor citation dedup", () => {
  it("collapses identical citations in one paragraph to a single aside", () => {
    const u = "https://ebicycles.example/hub"
    const html = render(
      `Claim${cite(u, "Hub vs Mid")} again${cite(u, "Hub vs Mid")}.`,
    )
    expect(html.match(/<shiny-aside\b(?!-group)/g)).toHaveLength(1)
  })
})
