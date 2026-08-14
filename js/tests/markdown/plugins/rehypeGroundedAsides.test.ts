import { describe, expect, it } from "vitest"
import rehypeStringify from "rehype-stringify"
import { unified } from "unified"
import {
  htmlProcessor,
  markdownProcessor,
} from "../../../src/markdown/processors"
import { parseHtml } from "../../../src/markdown/markdownToReact"

function render(markdown: string): string {
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

describe("rehypeGroundedAsides", () => {
  it("grounds an ordinary aside without citation metadata", () => {
    const html = render(`A supported claim${aside("supported claim")}.`)

    expect(html).toContain(
      '<span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">supported claim</span>',
    )
    expect(html).toContain('data-grounding-id="aside-grounding-1"')
  })

  it("matches the most recent exact occurrence before the aside", () => {
    const html = render(`repeat, then repeat${aside("repeat")}.`)

    expect(html).toContain('repeat, then <span class="shiny-aside-grounded"')
    expect(html).not.toContain(
      '<span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">repeat</span>, then repeat',
    )
  })

  it("preserves inline formatting across a grounded span", () => {
    const html = render(`A **supported** claim${aside("supported claim")}.`)

    expect(html).toContain(
      '<strong><span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">supported</span></strong><span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1"> claim</span>',
    )
  })

  it.each([
    ["emphasis", "A ***supported claim***", "***supported claim***"],
    ["inline code", "A `supported claim`", "`supported claim`"],
    [
      "link text",
      "A [supported claim](https://example.com)",
      "[supported claim](https://example.com)",
    ],
    [
      "an unmatched leading emphasis boundary",
      "The current stable Python release is **Python 3.14.6**, which was released on **June 10, 2026**.",
      "6**, which was released on **June 10, 2026**",
    ],
    [
      "an unmatched trailing emphasis boundary",
      "A **supported claim**",
      "**supported claim",
    ],
  ])("matches a grounded span with %s markup", (_name, answer, span) => {
    const html = render(`${answer}${aside(span)}.`)

    expect(html).toContain("shiny-aside-grounded")
    expect(html).toContain('data-grounding-id="aside-grounding-1"')
  })

  it("does nothing when the span is absent, unmatched, or after the aside", () => {
    const html = render(
      `Before${aside("supported claim")} supported claim, then another${aside("missing")}, and one${aside()}.`,
    )

    expect(html).not.toContain("shiny-aside-grounded")
    expect(html).not.toContain("data-grounding-id")
  })

  it("grounds ordinary asides in raw HTML paragraphs", () => {
    const tree = parseHtml(
      `<p>A supported claim${aside("supported claim")}.</p>`,
      htmlProcessor,
    )
    const html = String(
      unified()
        .use(rehypeStringify, { allowDangerousHtml: true })
        .stringify(tree),
    )

    expect(html).toContain(
      '<span class="shiny-aside-grounded" data-aside-grounding="aside-grounding-1">supported claim</span>',
    )
  })
})
