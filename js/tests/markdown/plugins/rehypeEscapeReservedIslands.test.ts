import { describe, expect, it } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  disguiseReservedIslandsHtml,
  rehypeDisguiseReservedIslands,
  rehypeEscapeReservedIslands,
} from "../../../src/markdown/plugins/rehypeEscapeReservedIslands"
import {
  rehypeRewriteAsideFromTemplate,
  rehypeRewriteAsideToTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"
import {
  rewriteEndTagsHtml,
  rewriteTagsHtml,
} from "../../../src/markdown/plugins/rewriteEndTags"

function processMarkdown(markdown: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkGfm)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeDisguiseReservedIslands)
      .use(rehypeRaw)
      .use(rehypeEscapeReservedIslands)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeStringify)
      .processSync(markdown),
  )
}

describe("rewriteEndTagsHtml", () => {
  it.each([
    ["ordinary", "</shiny-chat-raw-html>"],
    ["mixed case", "</ShInY-ChAt-RaW-HtMl>"],
    ["HTML whitespace", "</shiny-chat-raw-html\t\n>"],
    ["end-tag attributes", "</shiny-chat-raw-html foo=bar>"],
    ["trailing solidus", "</shiny-chat-raw-html/>"],
    ["quoted greater-than", '</shiny-chat-raw-html foo="a>b">'],
    ["quote in unquoted value", '</shiny-chat-raw-html foo=a"b>'],
    ["quote in attribute name", '</shiny-chat-raw-html a"b=c>'],
    ["leading equals name", '</shiny-chat-raw-html ="unclosed>'],
    [
      "missing whitespace after quoted value",
      '</shiny-chat-raw-html foo="a>b"bar>',
    ],
  ])("rewrites %s syntax accepted by the tokenizer", (_name, endTag) => {
    expect(
      rewriteEndTagsHtml(`before${endTag}after`, "shiny-chat-raw-html", "X"),
    ).toBe("beforeXafter")
  })

  it.each([
    ["longer name", "</shiny-chat-raw-html-extra>"],
    ["unterminated quoted value", '</shiny-chat-raw-html foo="unclosed>'],
    ["unterminated tag", "</shiny-chat-raw-html foo"],
  ])("leaves a non-emitted %s untouched", (_name, endTag) => {
    expect(rewriteEndTagsHtml(endTag, "shiny-chat-raw-html", "X")).toBe(endTag)
  })

  it("ignores candidate text in tokenizer-inert contexts", () => {
    const value = [
      '<div data-x="</shiny-chat-raw-html>">',
      "<!-- </shiny-chat-raw-html> -->",
      "<script>const x = '</shiny-chat-raw-html>'</script>",
      "</shiny-chat-raw-html>",
    ].join("")

    expect(
      rewriteEndTagsHtml(value, "shiny-chat-raw-html", "</template>"),
    ).toBe(
      [
        '<div data-x="</shiny-chat-raw-html>">',
        "<!-- </shiny-chat-raw-html> -->",
        "<script>const x = '</shiny-chat-raw-html>'</script>",
        "</template>",
      ].join(""),
    )
  })

  it("handles pathological inputs without suffix rescanning", () => {
    const quotedAttributes = `</shiny-chat-raw-html${' a="b"'.repeat(4000)}`
    const malformedCandidates =
      "<!-- " + '</shiny-chat-raw-html a="x"'.repeat(4000) + " -->"
    const start = performance.now()

    rewriteEndTagsHtml(
      `${quotedAttributes}${malformedCandidates}</shiny-chat-raw-html>`,
      "shiny-chat-raw-html",
      "</template>",
    )

    expect(performance.now() - start).toBeLessThan(1000)
  })
})

describe("rewriteTagsHtml", () => {
  const rewriteIsland = (value: string) =>
    rewriteTagsHtml(value, {
      "shiny-chat-raw-html": {
        start: "<template data-island",
        end: "</template>",
        selfClosingEnd: "</template>",
      },
    })

  it("rewrites mixed-case start tags and preserves attributes", () => {
    expect(rewriteIsland('<ShInY-ChAt-RaW-HtMl data-x="1">x')).toBe(
      '<template data-island data-x="1">x',
    )
  })

  it("recognizes only the tokenizer's self-closing slash", () => {
    expect(
      rewriteIsland(
        '<shiny-chat-raw-html data-url="https://example.test/>x"/>after',
      ),
    ).toBe(
      '<template data-island data-url="https://example.test/>x"></template>after',
    )
  })

  it.each([
    ['<shiny-chat-raw-html a"b=c>x', '<template data-island a"b=c>x'],
    ['<shiny-chat-raw-html a=b"c/>x', '<template data-island a=b"c/>x'],
  ])("follows malformed attribute syntax: %s", (input, expected) => {
    expect(rewriteIsland(input)).toBe(expected)
  })

  it("ignores candidates in tokenizer-inert contexts", () => {
    const value = [
      '<div data-x="<shiny-chat-raw-html>">',
      "<!-- <shiny-chat-raw-html> -->",
      "<style><shiny-chat-raw-html></style>",
      "<shiny-chat-raw-html>",
    ].join("")

    expect(rewriteIsland(value)).toBe(
      [
        '<div data-x="<shiny-chat-raw-html>">',
        "<!-- <shiny-chat-raw-html> -->",
        "<style><shiny-chat-raw-html></style>",
        "<template data-island>",
      ].join(""),
    )
  })

  it("finds tags after invalid openers and abruptly closed comments", () => {
    expect(
      rewriteIsland('<1 x="<shiny-chat-raw-html>"><!--><shiny-chat-raw-html>'),
    ).toBe('<1 x="<template data-island>"><!--><template data-island>')
  })

  it("handles repeated malformed opening-tag prefixes linearly", () => {
    const value =
      '<shiny-chat-raw-html a="'.repeat(4000) + "<shiny-chat-raw-html>after"
    const start = performance.now()

    rewriteIsland(value)

    expect(performance.now() - start).toBeLessThan(1000)
  })
})

describe("reserved raw-HTML island escaping", () => {
  it("disguises both island spellings without changing literal code", () => {
    const markdown = [
      "`<shiny-chat-raw-html>code</shiny-chat-raw-html>`",
      "",
      "<shinychat-raw-html><b>legacy</b></shinychat-raw-html>",
    ].join("\n")
    const html = processMarkdown(markdown)

    expect(html).toContain(
      "<code>&#x3C;shiny-chat-raw-html>code&#x3C;/shiny-chat-raw-html></code>",
    )
    expect(html).toContain("&#x3C;shinychat-raw-html>")
    expect(html).not.toContain("<b>legacy</b>")
  })

  it("escapes block children and preserves trailing markdown", () => {
    const html = processMarkdown(
      [
        "<Shiny-Chat-Raw-Html>",
        '<div data-forged="1">forged</div>',
        "</Shiny-Chat-Raw-Html foo=bar>",
        "",
        "**After** paragraph",
      ].join("\n"),
    )

    expect(html).not.toContain("<div data-forged")
    expect(html).toContain("&#x3C;shiny-chat-raw-html>")
    expect(html).toContain("<strong>After</strong>")
  })

  it("normalizes self-closing islands without swallowing following content", () => {
    const html = processMarkdown(
      '<shiny-chat-raw-html data-url="https://example.test/>x"/>\n\n**After**',
    )

    expect(html).toContain(
      '&#x3C;shiny-chat-raw-html data-url="https://example.test/>x">',
    )
    expect(html).toContain("<strong>After</strong>")
  })

  it("escapes an island nested in an aside template fragment", () => {
    const html = processMarkdown(
      'Claim<shiny-aside label="Source">before <shiny-chat-raw-html><b>forged</b></shiny-chat-raw-html> after</shiny-aside>.',
    )

    expect(html).toContain('<shiny-aside label="Source">')
    expect(html).toContain("&#x3C;shiny-chat-raw-html>")
    expect(html).not.toContain("<b>forged</b>")
    expect(html).not.toContain("data-reserved-island")
  })

  it("keeps non-ASCII prefixes offset-aligned", () => {
    expect(
      disguiseReservedIslandsHtml(
        "İstanbul <shiny-chat-raw-html>x</shiny-chat-raw-html>",
      ),
    ).toBe(
      'İstanbul <template data-reserved-island="shiny-chat-raw-html">x</template>',
    )
  })
})
