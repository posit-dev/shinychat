import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeGroupAsides } from "../../../src/markdown/plugins/rehypeGroupAsides"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeGroupAsides)
      .use(rehypeStringify)
      .processSync(md),
  )
}

describe("rehypeGroupAsides", () => {
  it("collapses a single aside into a one-entry group at the end of the paragraph", () => {
    const md =
      'A claim<shiny-aside label="eBicycles" url="https://ebicycles.example"></shiny-aside> continues here.'
    const html = process(md)
    expect(html).toContain("<p>A claim continues here.<shiny-aside-group>")
    expect(html.match(/<shiny-aside(?!-group)\b/g)).toHaveLength(1)
  })

  it("groups asides scattered through a paragraph into one trailing group, in document order", () => {
    const md = [
      'Torque matters<shiny-aside label="WIRED" url="https://wired.example"></shiny-aside>.',
      'Battery quality too<shiny-aside label="BikeRadar" url="https://bikeradar.example"></shiny-aside>.',
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(1)
    expect(html.match(/<shiny-aside(?!-group)\b/g)).toHaveLength(2)
    const groupStart = html.indexOf("<shiny-aside-group>")
    const firstAside = html.indexOf("<shiny-aside ")
    expect(firstAside).toBeGreaterThan(groupStart)
    // Original document order preserved inside the group.
    expect(html.indexOf('label="WIRED"')).toBeLessThan(
      html.indexOf('label="BikeRadar"'),
    )
  })

  it("keeps every same-label aside as a distinct entry in one group", () => {
    const md = [
      'First mention<shiny-aside label="eBicycles" url="https://ebicycles.example/a"></shiny-aside>.',
      'Second mention, same source<shiny-aside label="eBicycles" url="https://ebicycles.example/b"></shiny-aside>.',
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-aside(?!-group)\b/g)).toHaveLength(2)
    expect(html.match(/<shiny-aside-group\b/g)).toHaveLength(1)
    expect(html).toContain("https://ebicycles.example/a")
    expect(html).toContain("https://ebicycles.example/b")
  })

  it("splits every label-less aside into its own single-entry group", () => {
    const md = [
      "A number<shiny-aside>note one</shiny-aside>",
      "and another<shiny-aside>note two</shiny-aside>.",
    ].join(" ")
    const html = process(md)
    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(2)
    expect(html.match(/<shiny-aside(?!-group)\b/g)).toHaveLength(2)
  })

  it("stamps each anonymous aside with a sequential index, never consumed by labeled ones", () => {
    const md = [
      "Anon one<shiny-aside>note one</shiny-aside>.",
      'Cited claim<shiny-aside label="Source" url="https://x.example"></shiny-aside>.',
      "Anon two<shiny-aside>note two</shiny-aside>.",
    ].join(" ")
    const html = process(md)
    expect(html).toContain('<shiny-aside index="1">note one</shiny-aside>')
    expect(html).toContain('<shiny-aside index="2">note two</shiny-aside>')
  })

  it("places the bundled labeled group at the first labeled occurrence, anonymous singles at their own position", () => {
    const md = [
      "Anon claim<shiny-aside>note one</shiny-aside>,",
      'then a cited one<shiny-aside label="Source" url="https://x.example"></shiny-aside>.',
    ].join(" ")
    const html = process(md)
    const anonGroup = html.indexOf('index="1"')
    const labeledGroup = html.indexOf('label="Source"')
    expect(anonGroup).toBeLessThan(labeledGroup)
  })

  it("continues numbering across separate containers in one message", () => {
    const md = [
      "First paragraph, one anonymous claim<shiny-aside>a</shiny-aside>.",
      "",
      "Second paragraph, another anonymous claim<shiny-aside>b</shiny-aside>.",
    ].join("\n")
    const html = process(md)
    expect(html).toContain('<shiny-aside index="1">a</shiny-aside>')
    expect(html).toContain('<shiny-aside index="2">b</shiny-aside>')
  })

  it("groups asides in a tight list item", () => {
    const md =
      '- Item text<shiny-aside label="Source" url="https://x.example"></shiny-aside>'
    const html = process(md)
    expect(html).toContain("<li>Item text<shiny-aside-group>")
  })

  it("attaches an aside inside a nested list item's own <li>, not the outer one", () => {
    const md = [
      "- Item A",
      '  - Sub item B<shiny-aside label="X" url="https://x.example"></shiny-aside>',
      "- Item C",
    ].join("\n")
    const html = process(md)
    expect(html).toContain("<li>Sub item B<shiny-aside-group>")
    expect(html).not.toContain("<li>Item A<shiny-aside-group>")
  })

  it("leaves a block with no asides unchanged", () => {
    const html = process("Just plain prose.")
    expect(html).not.toContain("shiny-aside-group")
  })

  it("preserves an HTML-entity-escaped quote inside aside body text", () => {
    const md =
      'A claim<shiny-aside label="Source" url="https://x.example">A &quot;quoted phrase&quot; inside the body.</shiny-aside>.'
    const html = process(md)
    expect(html).toContain('A "quoted phrase" inside the body.')
  })
})
