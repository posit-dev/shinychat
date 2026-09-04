import { describe, expect, it } from "vitest"
import {
  rewriteEndTagsHtml,
  rewriteTagsHtml,
} from "../../../src/markdown/plugins/rewriteEndTags"

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
