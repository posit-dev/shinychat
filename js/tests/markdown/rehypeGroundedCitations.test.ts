import { describe, expect, it } from "vitest"
import rehypeStringify from "rehype-stringify"
import { unified } from "unified"
import { htmlProcessor, markdownProcessor } from "../../src/markdown/processors"
import { parseHtml } from "../../src/markdown/markdownToReact"

function render(markdown: string): string {
  const tree = markdownProcessor.runSync(markdownProcessor.parse(markdown))
  return String(
    unified()
      .use(rehypeStringify, { allowDangerousHtml: true })
      .stringify(tree),
  )
}

function citation(groundedSpan?: string): string {
  const grounding = groundedSpan ? ` grounded-span="${groundedSpan}"` : ""
  return `<shiny-aside data-citation label="example.com" url="https://example.com"${grounding}>Example</shiny-aside>`
}

describe("rehypeGroundedCitations", () => {
  it("marks an exact grounded span and connects it to the citation", () => {
    const html = render(`A supported claim${citation("supported claim")}.`)

    expect(html).toContain(
      '<span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1">supported claim</span>',
    )
    expect(html).toContain('data-grounding-id="citation-grounding-1"')
  })

  it("does nothing when grounded_span is absent or unmatched", () => {
    const html = render(
      `A supported claim${citation()} and another${citation("missing text")}.`,
    )

    expect(html).not.toContain("shiny-citation-grounded")
    expect(html).not.toContain("data-grounding-id")
  })

  it("does not normalize case or whitespace to find a match", () => {
    const html = render(`A supported claim${citation("Supported  claim")}.`)

    expect(html).not.toContain("shiny-citation-grounded")
    expect(html).not.toContain("data-grounding-id")
  })

  it("does not match text that appears only after the citation", () => {
    const html = render(`Before${citation("supported claim")} supported claim.`)

    expect(html).not.toContain("shiny-citation-grounded")
    expect(html).not.toContain("data-grounding-id")
  })

  it("matches the last exact occurrence before the citation", () => {
    const html = render(`repeat, then repeat${citation("repeat")}.`)

    expect(html).toContain('repeat, then <span class="shiny-citation-grounded"')
    expect(html).not.toContain(
      '<span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1">repeat</span>, then repeat',
    )
  })

  it("preserves inline formatting across a grounded span", () => {
    const html = render(`A **supported** claim${citation("supported claim")}.`)

    expect(html).toContain(
      '<strong><span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1">supported</span></strong><span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1"> claim</span>',
    )
  })

  it("connects overlapping citation occurrences to the same text", () => {
    const html = render(
      `A supported claim${citation("supported claim")}${citation("supported claim")}.`,
    )

    expect(html).toContain(
      'data-citation-grounding="citation-grounding-1 citation-grounding-2"',
    )
    expect(html).toContain('data-grounding-id="citation-grounding-1"')
    expect(html).toContain('data-grounding-id="citation-grounding-2"')
  })

  it("grounds citations in tight list items", () => {
    const html = render(`- A supported claim${citation("supported claim")}.`)

    expect(html).toContain(
      '<span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1">supported claim</span>',
    )
  })

  it("does not let a nested-list citation match outer item text", () => {
    const html = render(
      `- Outer claim\n  - Inner text${citation("Outer claim")}.`,
    )

    expect(html).not.toContain("shiny-citation-grounded")
    expect(html).not.toContain("data-grounding-id")
  })

  it("grounds citations in raw HTML paragraphs", () => {
    const tree = parseHtml(
      `<p>A supported claim${citation("supported claim")}.</p>`,
      htmlProcessor,
    )
    const html = String(
      unified()
        .use(rehypeStringify, { allowDangerousHtml: true })
        .stringify(tree),
    )

    expect(html).toContain(
      '<span class="shiny-citation-grounded" data-citation-grounding="citation-grounding-1">supported claim</span>',
    )
  })
})
