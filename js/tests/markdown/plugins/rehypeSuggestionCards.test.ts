import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  rehypeSuggestionCards,
  finalizePendingSuggestionLists,
} from "../../../src/markdown/plugins/rehypeSuggestionCards"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"
import type { Root } from "hast"

// Simulates the end-of-stream render: rehype + finalization (streaming=false).
function process(md: string): string {
  const proc = unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSuggestionCards)
    .use(() => (tree) => {
      finalizePendingSuggestionLists(tree as Root)
    })
    .use(rehypeStringify)
  return String(proc.processSync(md))
}

// Simulates a mid-stream render: rehype without finalization.
function processStreaming(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeSuggestionCards)
      .use(rehypeStringify)
      .processSync(md),
  )
}

function processWithA11y(md: string): string {
  const proc = unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeAccessibleSuggestions)
    .use(rehypeSuggestionCards)
    .use(() => (tree) => {
      finalizePendingSuggestionLists(tree as Root)
    })
    .use(rehypeStringify)
  return String(proc.processSync(md))
}

describe("rehypeSuggestionCards", () => {
  describe("basic ul promotion", () => {
    it("promotes a ul of three body-only suggestion spans", () => {
      const md = [
        "- <span class='suggestion'>First option</span>",
        "- <span class='suggestion'>Second option</span>",
        "- <span class='suggestion'>Third option</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).not.toContain("shiny-chat-suggestion-list--ordered")
      expect(html).toContain("shiny-chat-suggestion-list-item")
      expect(html).toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("shiny-chat-suggestion-list-item-title")
      expect(html).toContain('data-suggestion="First option"')
      expect(html).toContain('data-suggestion="Second option"')
      expect(html).toContain('data-suggestion="Third option"')
    })

    it("sets data-suggestion to body text, not title text", () => {
      const md = [
        "- <span class='suggestion' title='Card heading'>body text here</span>",
        "- <span class='suggestion' title='Another heading'>more body</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain('data-suggestion="body text here"')
      expect(html).toContain('data-suggestion="more body"')
      expect(html).not.toContain('data-suggestion="Card heading"')
      expect(html).not.toContain('data-suggestion="Another heading"')
    })

    it("renders title divs when title attribute is present on ul items", () => {
      const md = [
        "- <span class='suggestion' title='Alpha'>first body</span>",
        "- <span class='suggestion' title='Beta'>second body</span>",
        "- <span class='suggestion' title='Gamma'>third body</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list-item-title")
      expect(html).toContain("Alpha")
      expect(html).toContain("Beta")
      expect(html).toContain("Gamma")
      expect(html).toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("title=")
    })
  })

  describe("ol promotion", () => {
    it("promotes a ol and adds --ordered class", () => {
      const md = [
        "1. <span class='suggestion' title='Foo'>do foo</span>",
        "2. <span class='suggestion' title='Bar'>do bar</span>",
        "3. <span class='suggestion' title='Baz'>do baz</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list--ordered")
      expect(html).toContain("shiny-chat-suggestion-list-item-title")
      expect(html).toContain("1. Foo")
      expect(html).toContain("2. Bar")
      expect(html).toContain("3. Baz")
    })

    it("renders numbered-only titles for ol items without title attribute", () => {
      const md = [
        "1. <span class='suggestion'>first</span>",
        "2. <span class='suggestion'>second</span>",
        "3. <span class='suggestion'>third</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list--ordered")
      expect(html).toContain("shiny-chat-suggestion-list-item-title")
      expect(html).toContain(">1.<")
      expect(html).toContain(">2.<")
      expect(html).toContain(">3.<")
    })
  })

  describe("mixed cases", () => {
    it("handles a ul with mixed titled and untitled items", () => {
      const md = [
        "- <span class='suggestion' title='With title'>body one</span>",
        "- <span class='suggestion'>no title body</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("With title")
      expect(html).toContain("shiny-chat-suggestion-list-item-body")
    })

    it("promotes a single-item ul", () => {
      const md = "- <span class='suggestion'>single item</span>"

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("shiny-chat-suggestion-list-item")
      expect(html).toContain('data-suggestion="single item"')
    })
  })

  describe("non-qualifying lists", () => {
    it("does not promote an empty ul", () => {
      const html = process("<ul></ul>")

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })

    it("does not promote a li with a suggestion span plus trailing text", () => {
      const md = [
        "- <span class='suggestion'>option</span> extra text",
        "- <span class='suggestion'>option two</span>",
        "",
        "Trailing block.",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("data-pending")
    })

    it("does not promote a li with two suggestion spans", () => {
      const md = [
        "- <span class='suggestion'>one</span><span class='suggestion'>two</span>",
        "- <span class='suggestion'>three</span>",
        "",
        "Trailing block.",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("data-pending")
    })

    it("does not promote a li with a suggestion class span and a data-suggestion span", () => {
      const md = [
        "- <span class='suggestion'>one</span><span data-suggestion='two'>label</span>",
        "- <span class='suggestion'>three</span>",
        "",
        "Trailing block.",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("data-pending")
    })

    it("does not promote a list with plain-text li items", () => {
      const md = [
        "- plain text item",
        "- <span class='suggestion'>option</span>",
        "",
        "Trailing block.",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("data-pending")
    })

    it("does not promote a qualifying ul nested inside another ul", () => {
      const md = [
        "- outer item",
        "  - <span class='suggestion'>inner one</span>",
        "  - <span class='suggestion'>inner two</span>",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })

    it("does not promote a qualifying ul inside a blockquote", () => {
      const md = [
        "> - <span class='suggestion'>nested one</span>",
        "> - <span class='suggestion'>nested two</span>",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })
  })

  describe("whitespace tolerance", () => {
    it("promotes a list with whitespace-only text siblings inside li", () => {
      const md = [
        "- <span class='suggestion'>option one</span>",
        "- <span class='suggestion'>option two</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
    })
  })

  describe("mixed content after qualifying list", () => {
    it("only transforms the qualifying list, not following content", () => {
      const md = [
        "- <span class='suggestion'>option one</span>",
        "- <span class='suggestion'>option two</span>",
        "",
        "Some follow-up text.",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("Some follow-up text.")
      expect(html).not.toContain(
        'class="shiny-chat-suggestion-list">Some follow-up',
      )
    })
  })

  describe("pre-existing data-suggestion", () => {
    it("preserves existing data-suggestion and does not overwrite it", () => {
      const md = [
        "- <span class='suggestion' title='Label' data-suggestion='actual prompt'>visible text</span>",
        "- <span class='suggestion'>other option</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain('data-suggestion="actual prompt"')
      expect(html).not.toContain('data-suggestion="visible text"')
      expect(html).toContain("Label")
    })
  })

  describe("nested markdown body", () => {
    it("preserves nested HAST nodes in body div and computes text for data-suggestion", () => {
      const md = "- <span class='suggestion'><strong>bold</strong> text</span>"

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list-item-body")
      expect(html).toContain("<strong>bold</strong>")
      expect(html).toContain('data-suggestion="bold text"')
    })
  })

  describe("tag-agnostic detection", () => {
    it("promotes a list where img with data-suggestion is the sole li child", () => {
      const md = [
        "- <img data-suggestion='prompt one' src='a.png' alt='one'>",
        "- <img data-suggestion='prompt two' src='b.png' alt='two'>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("shiny-chat-suggestion-list-item")
    })
  })

  describe("pending suggestion lists (mid-stream)", () => {
    it("marks data-pending when a trailing list has one suggestion and one empty li", () => {
      const md = ["- <span class='suggestion'>first option</span>", "- "].join(
        "\n",
      )

      const html = processStreaming(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("data-pending")
      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
    })

    it("does not mark a regular list with plain-text items as pending", () => {
      const md = ["- first item text", "- "].join("\n")

      const html = processStreaming(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
      expect(html).not.toContain("data-pending")
    })

    it("does not mark a list of only empty li as pending", () => {
      const md = ["- ", "- "].join("\n")

      const html = processStreaming(md)

      expect(html).not.toContain("data-pending")
    })

    it("does not mark as pending when the list is not the last top-level child", () => {
      const md = [
        "- <span class='suggestion'>first</span>",
        "- ",
        "",
        "trailing text",
      ].join("\n")

      const html = processStreaming(md)

      expect(html).not.toContain("data-pending")
    })

    it("keeps a fully qualifying trailing list pending mid-stream (does not promote)", () => {
      const md = [
        "- <span class='suggestion'>first</span>",
        "- <span class='suggestion'>second</span>",
      ].join("\n")

      const html = processStreaming(md)

      expect(html).toContain("data-pending")
      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
    })

    it("promotes a fully qualifying list after finalization (end of stream)", () => {
      const md = [
        "- <span class='suggestion'>first</span>",
        "- <span class='suggestion'>second</span>",
      ].join("\n")

      const html = process(md)

      expect(html).toContain("shiny-chat-suggestion-list-item-body")
      expect(html).not.toContain("data-pending")
    })

    it("strips pending markers from a non-qualifying list after finalization", () => {
      const md = [
        "- <span class='suggestion'>only suggestion</span>",
        "- plain text item",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("data-pending")
      expect(html).not.toContain("shiny-chat-suggestion-list")
      expect(html).not.toContain("shiny-chat-suggestion-list-item-body")
    })

    it("marks ordered pending lists as well", () => {
      const md = [
        "1. <span class='suggestion'>first option</span>",
        "1. ",
      ].join("\n")

      const html = processStreaming(md)

      expect(html).toContain("shiny-chat-suggestion-list--ordered")
      expect(html).toContain("data-pending")
    })

    it("stays pending when a later li contains partial raw-html text", () => {
      // mid-stream snapshot: first <li> is a complete suggestion, second
      // <li> contains a partial open tag the parser has surfaced as text.
      const md = [
        "<ul>",
        "<li><span class='suggestion'>first option</span></li>",
        "<li>&lt;span class=&quot;suggestion&quot;</li>",
        "</ul>",
      ].join("\n")

      const html = processStreaming(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain("data-pending")
    })

    it("stays pending when a later li has a complete suggestion next to text", () => {
      // first <li> already a complete suggestion; second <li> has
      // unrelated text (could be a half-typed item before the model
      // adds the next suggestion).
      const md = [
        "- <span class='suggestion'>first option</span>",
        "- some text that has not yet become a suggestion",
      ].join("\n")

      const html = processStreaming(md)

      expect(html).toContain("data-pending")
    })
  })

  describe("end-to-end with rehypeAccessibleSuggestions", () => {
    it("cards also get tabindex and role from rehypeAccessibleSuggestions", () => {
      const md = [
        "- <span class='suggestion'>option one</span>",
        "- <span class='suggestion'>option two</span>",
      ].join("\n")

      const html = processWithA11y(md)

      expect(html).toContain("shiny-chat-suggestion-list")
      expect(html).toContain('tabindex="0"')
      expect(html).toContain('role="button"')
    })
  })
})
