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

  it("groups label-less web citations by their inferred domain label", () => {
    const md = [
      'First claim<shiny-aside data-citation url="https://www.python.org/downloads/"></shiny-aside>.',
      'Second claim<shiny-aside data-citation url="https://www.python.org/doc/versions/"></shiny-aside>.',
    ].join(" ")
    const html = process(md)

    expect(html.match(/<shiny-aside-group\b/g)).toHaveLength(1)
    expect(html.match(/<shiny-aside(?!-group)\b/g)).toHaveLength(2)
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

  it("groups compact labeled asides from the same block", () => {
    const md = [
      'First<shiny-aside display="compact" label="Source A">a</shiny-aside>',
      'second<shiny-aside display="compact" label="Source B">b</shiny-aside>.',
    ].join(" ")
    const html = process(md)

    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(1)
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source A" index="1">',
    )
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source B" index="2">',
    )
  })

  it("keeps compact labeled asides from separate blocks in separate groups", () => {
    const md = [
      'First<shiny-aside display="compact" label="Source A">a</shiny-aside>.',
      "",
      'Second<shiny-aside display="compact" label="Source B">b</shiny-aside>.',
    ].join("\n")
    const html = process(md)

    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(2)
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source A" index="1">',
    )
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source B" index="2">',
    )
  })

  it("numbers anonymous and compact labeled asides in document order", () => {
    const md = [
      "Anonymous<shiny-aside>a</shiny-aside>.",
      'Compact label<shiny-aside display="compact" label="Source">b</shiny-aside>.',
      'Ordinary label<shiny-aside label="Chip">c</shiny-aside>.',
      "Anonymous again<shiny-aside>d</shiny-aside>.",
    ].join("\n\n")
    const html = process(md)

    expect(html).toContain('<shiny-aside index="1">a</shiny-aside>')
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source" index="2">',
    )
    expect(html).toContain('<shiny-aside index="3">d</shiny-aside>')
    expect(html).not.toContain('label="Chip" index=')
  })

  it("preserves count marker indexes when marker types interleave in one block", () => {
    const md = [
      'First<shiny-aside display="compact" label="Source A">a</shiny-aside>,',
      "anonymous<shiny-aside>b</shiny-aside>,",
      'third<shiny-aside display="compact" label="Source C">c</shiny-aside>.',
    ].join(" ")
    const html = process(md)

    expect(html).toContain(
      '<shiny-aside display="compact" label="Source A" index="1">',
    )
    expect(html).toContain('<shiny-aside index="2">b</shiny-aside>')
    expect(html).toContain(
      '<shiny-aside display="compact" label="Source C" index="3">',
    )
  })

  it("ignores unsupported display values and the former marker spelling", () => {
    const md = [
      'First<shiny-aside display="label" label="Source A">a</shiny-aside>',
      'second<shiny-aside display="bogus" label="Source B">b</shiny-aside>.',
      'third<shiny-aside marker="number" label="Source C">c</shiny-aside>.',
    ].join(" ")
    const html = process(md)

    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(1)
    expect(html).not.toContain('index="')
  })

  it("does not change native web citations without an explicit compact display", () => {
    const md = [
      'First<shiny-aside data-citation label="A" url="https://a.example">a</shiny-aside>',
      'second<shiny-aside data-citation label="B" url="https://b.example">b</shiny-aside>.',
    ].join(" ")
    const html = process(md)

    expect(html.match(/<shiny-aside-group>/g)).toHaveLength(1)
    expect(html).not.toContain('index="')
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

  it("removes a trailing break before an inline aside group", () => {
    const html = process(
      '<p>Item text<br>\n<shiny-aside label="Source">Details</shiny-aside></p>',
    )

    expect(html).toContain(
      '<p>Item text<shiny-aside-group><shiny-aside label="Source">Details</shiny-aside></shiny-aside-group></p>',
    )
    expect(html).not.toContain("<br>")
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
