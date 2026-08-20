import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import type { Root } from "hast"
import { rehypeAttachAsidesToPreviousParagraph } from "../../../src/markdown/plugins/rehypeAttachAsidesToPreviousParagraph"
import { rehypeGroupAsides } from "../../../src/markdown/plugins/rehypeGroupAsides"
import {
  rehypeMarkTrailingAsides,
  finalizePendingAsides,
} from "../../../src/markdown/plugins/markTrailingAsides"

// Simulates a mid-stream render: group + mark, no finalization.
function processStreaming(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeAttachAsidesToPreviousParagraph)
      .use(rehypeGroupAsides)
      .use(rehypeMarkTrailingAsides)
      .use(rehypeStringify)
      .processSync(md),
  )
}

// Simulates the end-of-stream render: group + mark + finalization.
function process(md: string): string {
  const proc = unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeAttachAsidesToPreviousParagraph)
    .use(rehypeGroupAsides)
    .use(rehypeMarkTrailingAsides)
    .use(() => (tree, _file, next) => {
      const result = finalizePendingAsides(tree as Root)
      if (result !== tree) Object.assign(tree, result)
      next()
    })
    .use(rehypeStringify)
  return String(proc.processSync(md))
}

describe("rehypeMarkTrailingAsides", () => {
  it("marks an aside group in the sole (still-open) paragraph as pending mid-stream", () => {
    const md =
      'A claim<shiny-aside label="Source" url="https://x.example"></shiny-aside> and more text'
    const html = processStreaming(md)
    expect(html).toContain("<shiny-aside-group data-pending")
  })

  it("does not mark a group whose paragraph has closed (a later block follows)", () => {
    const md = [
      'A claim<shiny-aside label="Source" url="https://x.example"></shiny-aside>.',
      "",
      "A second paragraph still streaming",
    ].join("\n")
    const html = processStreaming(md)
    expect(html).not.toContain("data-pending")
  })

  it("marks only the trailing paragraph's group when both paragraphs carry asides", () => {
    const md = [
      'First claim<shiny-aside label="One" url="https://one.example"></shiny-aside>.',
      "",
      'Second claim<shiny-aside label="Two" url="https://two.example"></shiny-aside> still going',
    ].join("\n")
    const html = processStreaming(md)
    // Exactly one group is pending (the trailing one).
    expect(html.match(/data-pending/g)).toHaveLength(1)
    // The pending marker sits with the trailing paragraph's source.
    const pendingIdx = html.indexOf("data-pending")
    expect(html.indexOf('label="Two"')).toBeGreaterThan(pendingIdx)
    expect(html.indexOf('label="One"')).toBeLessThan(pendingIdx)
  })

  it("marks the trailing tight-list item's aside pending, not an earlier item's", () => {
    const md = [
      '- Item A<shiny-aside label="A" url="https://a.example"></shiny-aside>',
      '- Item B<shiny-aside label="B" url="https://b.example"></shiny-aside>',
    ].join("\n")
    const html = processStreaming(md)
    expect(html.match(/data-pending/g)).toHaveLength(1)
    const pendingIdx = html.indexOf("data-pending")
    expect(html.indexOf('label="B"')).toBeGreaterThan(pendingIdx)
    expect(html.indexOf('label="A"')).toBeLessThan(pendingIdx)
  })

  it("marks a blank-line aside as pending in its attached trailing paragraph", () => {
    const md = [
      "A claim.",
      "",
      '<shiny-aside label="Source" url="https://x.example"></shiny-aside>',
    ].join("\n")

    const html = processStreaming(md)

    expect(html.match(/<p>/g)).toHaveLength(1)
    expect(html).toContain("<p>A claim.<shiny-aside-group data-pending")
  })

  it("leaves a message with no asides untouched", () => {
    const html = processStreaming("Just plain prose that keeps going")
    expect(html).not.toContain("data-pending")
  })

  it("removes all pending markers after finalization (stream end)", () => {
    const md =
      'A claim<shiny-aside label="Source" url="https://x.example"></shiny-aside> and more text'
    const html = process(md)
    expect(html).not.toContain("data-pending")
    expect(html).toContain("<shiny-aside-group>")
  })
})
