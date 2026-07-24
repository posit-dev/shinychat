import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import type { Root } from "hast"
import { rehypeGroupSidenotes } from "../../../src/markdown/plugins/rehypeGroupSidenotes"
import {
  rehypeMarkTrailingSidenotes,
  finalizePendingSidenotes,
} from "../../../src/markdown/plugins/markTrailingSidenotes"

// Simulates a mid-stream render: group + mark, no finalization.
function processStreaming(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeGroupSidenotes)
      .use(rehypeMarkTrailingSidenotes)
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
    .use(rehypeGroupSidenotes)
    .use(rehypeMarkTrailingSidenotes)
    .use(() => (tree, _file, next) => {
      const result = finalizePendingSidenotes(tree as Root)
      if (result !== tree) Object.assign(tree, result)
      next()
    })
    .use(rehypeStringify)
  return String(proc.processSync(md))
}

describe("rehypeMarkTrailingSidenotes", () => {
  it("marks a sidenote group in the sole (still-open) paragraph as pending mid-stream", () => {
    const md =
      'A claim<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote> and more text'
    const html = processStreaming(md)
    expect(html).toContain("<shiny-sidenote-group data-pending")
  })

  it("does not mark a group whose paragraph has closed (a later block follows)", () => {
    const md = [
      'A claim<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote>.',
      "",
      "A second paragraph still streaming",
    ].join("\n")
    const html = processStreaming(md)
    expect(html).not.toContain("data-pending")
  })

  it("marks only the trailing paragraph's group when both paragraphs carry sidenotes", () => {
    const md = [
      'First claim<shiny-sidenote label="One" url="https://one.example"></shiny-sidenote>.',
      "",
      'Second claim<shiny-sidenote label="Two" url="https://two.example"></shiny-sidenote> still going',
    ].join("\n")
    const html = processStreaming(md)
    // Exactly one group is pending (the trailing one).
    expect(html.match(/data-pending/g)).toHaveLength(1)
    // The pending marker sits with the trailing paragraph's source.
    const pendingIdx = html.indexOf("data-pending")
    expect(html.indexOf('label="Two"')).toBeGreaterThan(pendingIdx)
    expect(html.indexOf('label="One"')).toBeLessThan(pendingIdx)
  })

  it("marks the trailing tight-list item's sidenote pending, not an earlier item's", () => {
    const md = [
      '- Item A<shiny-sidenote label="A" url="https://a.example"></shiny-sidenote>',
      '- Item B<shiny-sidenote label="B" url="https://b.example"></shiny-sidenote>',
    ].join("\n")
    const html = processStreaming(md)
    expect(html.match(/data-pending/g)).toHaveLength(1)
    const pendingIdx = html.indexOf("data-pending")
    expect(html.indexOf('label="B"')).toBeGreaterThan(pendingIdx)
    expect(html.indexOf('label="A"')).toBeLessThan(pendingIdx)
  })

  it("leaves a message with no sidenotes untouched", () => {
    const html = processStreaming("Just plain prose that keeps going")
    expect(html).not.toContain("data-pending")
  })

  it("removes all pending markers after finalization (stream end)", () => {
    const md =
      'A claim<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote> and more text'
    const html = process(md)
    expect(html).not.toContain("data-pending")
    expect(html).toContain("<shiny-sidenote-group>")
  })
})
