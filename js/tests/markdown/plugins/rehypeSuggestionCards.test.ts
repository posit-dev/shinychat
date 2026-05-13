import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import { rehypeSuggestionCards } from "../../../src/markdown/plugins/rehypeSuggestionCards"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"

function process(md: string): string {
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
  return String(
    unified()
      .use(remarkParse)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRaw)
      .use(rehypeAccessibleSuggestions)
      .use(rehypeSuggestionCards)
      .use(rehypeStringify)
      .processSync(md),
  )
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
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })

    it("does not promote a li with two suggestion spans", () => {
      const md = [
        "- <span class='suggestion'>one</span><span class='suggestion'>two</span>",
        "- <span class='suggestion'>three</span>",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })

    it("does not promote a li with a suggestion class span and a data-suggestion span", () => {
      const md = [
        "- <span class='suggestion'>one</span><span data-suggestion='two'>label</span>",
        "- <span class='suggestion'>three</span>",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
    })

    it("does not promote a list with plain-text li items", () => {
      const md = [
        "- plain text item",
        "- <span class='suggestion'>option</span>",
      ].join("\n")

      const html = process(md)

      expect(html).not.toContain("shiny-chat-suggestion-list")
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
