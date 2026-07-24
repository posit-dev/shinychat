import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeGroupSidenotes } from "../../../src/markdown/plugins/rehypeGroupSidenotes"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeGroupSidenotes)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeGroupSidenotes", () => {
  it("collapses a single sidenote into a one-entry group at the end of the paragraph", () => {
    const md =
      'A claim<shiny-sidenote label="eBicycles" url="https://ebicycles.example"></shiny-sidenote> continues here.'
    const html = process(md)
    expect(html).toContain("<p>A claim continues here.<shiny-sidenote-group>")
    expect(html.match(/<shiny-sidenote(?!-group)\b/g)).toHaveLength(1)
  })

  it("groups sidenotes scattered through a paragraph into one trailing group, in document order", () => {
    const md = [
      'Torque matters<shiny-sidenote label="WIRED" url="https://wired.example"></shiny-sidenote>.',
      'Battery quality too<shiny-sidenote label="BikeRadar" url="https://bikeradar.example"></shiny-sidenote>.',
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-sidenote-group>/g)).toHaveLength(1)
    expect(html.match(/<shiny-sidenote(?!-group)\b/g)).toHaveLength(2)
    const groupStart = html.indexOf("<shiny-sidenote-group>")
    const firstSidenote = html.indexOf("<shiny-sidenote ")
    expect(firstSidenote).toBeGreaterThan(groupStart)
    // Original document order preserved inside the group.
    expect(html.indexOf('label="WIRED"')).toBeLessThan(
      html.indexOf('label="BikeRadar"'),
    )
  })

  it("dedupes sidenotes sharing the same label, keeping the first occurrence", () => {
    const md = [
      'First mention<shiny-sidenote label="eBicycles" url="https://ebicycles.example/a"></shiny-sidenote>.',
      'Second mention, same source<shiny-sidenote label="eBicycles" url="https://ebicycles.example/b"></shiny-sidenote>.',
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-sidenote(?!-group)\b/g)).toHaveLength(1)
    expect(html).toContain("https://ebicycles.example/a")
    expect(html).not.toContain("https://ebicycles.example/b")
  })

  it("splits every label-less sidenote into its own single-entry group", () => {
    const md = [
      "A number<shiny-sidenote>note one</shiny-sidenote>",
      "and another<shiny-sidenote>note two</shiny-sidenote>.",
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-sidenote-group>/g)).toHaveLength(2)
    expect(html.match(/<shiny-sidenote(?!-group)\b/g)).toHaveLength(2)
  })

  it("stamps each anonymous sidenote with a sequential index, never consumed by labeled ones", () => {
    const md = [
      "Anon one<shiny-sidenote>note one</shiny-sidenote>.",
      'Cited claim<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote>.',
      "Anon two<shiny-sidenote>note two</shiny-sidenote>.",
    ].join(" ")
    const html = process(md)
    expect(html).toContain(
      '<shiny-sidenote index="1">note one</shiny-sidenote>',
    )
    expect(html).toContain(
      '<shiny-sidenote index="2">note two</shiny-sidenote>',
    )
  })

  it("places the bundled labeled group at the first labeled occurrence, anonymous singles at their own position", () => {
    const md = [
      "Anon claim<shiny-sidenote>note one</shiny-sidenote>,",
      'then a cited one<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote>.',
    ].join(" ")
    const html = process(md)
    const anonGroup = html.indexOf('index="1"')
    const labeledGroup = html.indexOf('label="Source"')
    expect(anonGroup).toBeLessThan(labeledGroup)
  })

  it("continues numbering across separate containers in one message", () => {
    const md = [
      "First paragraph, one anonymous claim<shiny-sidenote>a</shiny-sidenote>.",
      "",
      "Second paragraph, another anonymous claim<shiny-sidenote>b</shiny-sidenote>.",
    ].join("\n")
    const html = process(md)
    expect(html).toContain('<shiny-sidenote index="1">a</shiny-sidenote>')
    expect(html).toContain('<shiny-sidenote index="2">b</shiny-sidenote>')
  })

  it("groups sidenotes in a tight list item", () => {
    const md =
      '- Item text<shiny-sidenote label="Source" url="https://x.example"></shiny-sidenote>'
    const html = process(md)
    expect(html).toContain("<li>Item text<shiny-sidenote-group>")
  })

  it("attaches a sidenote inside a nested list item's own <li>, not the outer one", () => {
    const md = [
      "- Item A",
      '  - Sub item B<shiny-sidenote label="X" url="https://x.example"></shiny-sidenote>',
      "- Item C",
    ].join("\n")
    const html = process(md)
    expect(html).toContain("<li>Sub item B<shiny-sidenote-group>")
    expect(html).not.toContain("<li>Item A<shiny-sidenote-group>")
  })

  it("leaves a block with no sidenotes unchanged", () => {
    const html = process("Just plain prose.")
    expect(html).not.toContain("shiny-sidenote-group")
  })

  it("preserves an HTML-entity-escaped quote inside sidenote body text", () => {
    const md =
      'A claim<shiny-sidenote label="Source" url="https://x.example">A &quot;quoted phrase&quot; inside the body.</shiny-sidenote>.'
    const html = process(md)
    expect(html).toContain('A "quoted phrase" inside the body.')
  })
})
