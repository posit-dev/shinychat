import { describe, it, expect } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import type { Element, Root } from "hast"
import {
  rehypeRewriteAsideToTemplate,
  rehypeRewriteAsideFromTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"
import { markdownProcessor } from "../../../src/markdown/processors"
import { parseMarkdown } from "../../../src/markdown/markdownToReact"

function process(md: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkGfm)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeRaw)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeStringify)
      .processSync(md),
  )
}

function findElements(node: Root | Element, tagName: string): Element[] {
  const found: Element[] = []
  for (const child of node.children) {
    if (child.type !== "element") continue
    if (child.tagName === tagName) found.push(child)
    found.push(...findElements(child, tagName))
  }
  return found
}

describe("rewriteAsideTemplate round-trip", () => {
  it("keeps an inline aside inline with its text as children", () => {
    const html = process(
      'A claim<shiny-aside label="eBicycles">a **bold** note</shiny-aside>.',
    )
    expect(html).not.toContain("<template")
    expect(html).toContain(
      '<shiny-aside label="eBicycles">a <strong>bold</strong> note</shiny-aside>',
    )
    expect(html).toContain("<p>A claim<shiny-aside")
  })

  it("nests a blank-line block body as children of the still-inline aside", () => {
    const html = process(
      'See notes<shiny-aside label="Study">\n\n**Key**\n\n- a\n- b\n\n</shiny-aside>.',
    )
    expect(html).not.toContain("<template")
    const open = html.indexOf("<shiny-aside")
    const close = html.indexOf("</shiny-aside>")
    const inner = html.slice(open, close)
    expect(inner).toContain("<strong>Key</strong>")
    expect(inner).toContain("<ul>")
    expect(inner).toContain("<li>a</li>")
    expect(inner).toContain("<li>b</li>")
    expect(html).toContain("<p>See notes<shiny-aside")
  })

  it("preserves label/url/icon attributes", () => {
    const html = process(
      'X<shiny-aside label="L" url="https://e.example" icon="https://e.example/i.png">n</shiny-aside>.',
    )
    expect(html).toContain('label="L"')
    expect(html).toContain('url="https://e.example"')
    expect(html).toContain('icon="https://e.example/i.png"')
    expect(html).not.toContain("data-shiny-aside")
  })

  it("treats a self-closing aside as empty, not swallowing following text", () => {
    const html = process(
      'A claim<shiny-aside label="x" url="https://e.example"/> and more text after.',
    )
    expect(html).not.toContain("<template")
    expect(html).toContain(
      '<shiny-aside label="x" url="https://e.example"></shiny-aside>',
    )
    // The trailing prose stays in the paragraph rather than becoming the body.
    expect(html).toContain("</shiny-aside> and more text after.</p>")
  })

  it("does not mistake a slash inside a quoted attribute for the self-close", () => {
    const html = process(
      'A claim<shiny-aside url="https://e.example/path/"/> tail.',
    )
    expect(html).toContain(
      '<shiny-aside url="https://e.example/path/"></shiny-aside>',
    )
    expect(html).toContain("</shiny-aside> tail.</p>")
  })

  it("does not rewrite an aside tag written literally inside a code fence", () => {
    const html = process("```\n<shiny-aside>x</shiny-aside>\n```")
    expect(html).not.toContain("<template")
    // The literal text is escaped inside <code>, so no real element appears.
    expect(html).not.toContain("<shiny-aside")
  })

  it("leaves aside markup literal inside an inline code span", () => {
    const tree = parseMarkdown(
      "`<shiny-aside>literal</shiny-aside>`",
      markdownProcessor,
    )
    expect(findElements(tree, "shiny-aside")).toHaveLength(0)
    expect(findElements(tree, "code")).toHaveLength(1)
  })

  it("leaves aside markup literal inside a fenced code block", () => {
    const tree = parseMarkdown(
      "```\n<shiny-aside>literal</shiny-aside>\n```",
      markdownProcessor,
    )
    expect(findElements(tree, "shiny-aside")).toHaveLength(0)
    expect(findElements(tree, "code")).toHaveLength(1)
  })

  it("keeps rich asides attached to adjacent top-level list items", () => {
    const markdown = [
      "- First claim.",
      '<shiny-aside label="Source A">',
      "",
      "**Reason A**",
      "",
      "> Exact supporting quote A.",
      "",
      "*Quoted verbatim; matched exactly.*",
      "",
      "</shiny-aside>",
      "",
      "- Second claim.",
      '<shiny-aside label="Source B">',
      "",
      "**Reason B**",
      "",
      "> Exact supporting quote B.",
      "",
      "*Quoted verbatim; matched exactly.*",
      "",
      "</shiny-aside>",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const topLevelLists = tree.children.filter(
      (child): child is Element =>
        child.type === "element" && child.tagName === "ul",
    )
    const topLevelItems = topLevelLists.flatMap((list) =>
      list.children.filter(
        (child): child is Element =>
          child.type === "element" && child.tagName === "li",
      ),
    )
    expect(topLevelItems).toHaveLength(2)
    expect(findElements(topLevelItems[0]!, "li")).toHaveLength(0)
    expect(findElements(topLevelItems[1]!, "li")).toHaveLength(0)
    expect(findElements(topLevelItems[0]!, "shiny-aside-group")).toHaveLength(1)
    expect(findElements(topLevelItems[0]!, "strong")).toHaveLength(1)
    expect(findElements(topLevelItems[0]!, "blockquote")).toHaveLength(1)
    expect(findElements(topLevelItems[0]!, "em")).toHaveLength(1)
    expect(findElements(topLevelItems[1]!, "shiny-aside-group")).toHaveLength(1)
    expect(findElements(topLevelItems[1]!, "strong")).toHaveLength(1)
    expect(findElements(topLevelItems[1]!, "blockquote")).toHaveLength(1)
    expect(findElements(topLevelItems[1]!, "em")).toHaveLength(1)
  })

  it("keeps a rich aside attached to its nested list item", () => {
    const markdown = [
      "- Outer item",
      "  - Nested claim.",
      '  <shiny-aside label="Nested">',
      "",
      "  **Nested reason**",
      "",
      "  > Nested quote.",
      "",
      "  *Nested note.*",
      "",
      "  </shiny-aside>",
      "- Next outer item",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const topLevelList = findElements(tree, "ul")[0]!
    const topLevelItems = topLevelList.children.filter(
      (child): child is Element =>
        child.type === "element" && child.tagName === "li",
    )
    expect(topLevelItems).toHaveLength(2)

    const nestedList = findElements(topLevelItems[0]!, "ul")[0]!
    const nestedItems = nestedList.children.filter(
      (child): child is Element =>
        child.type === "element" && child.tagName === "li",
    )
    expect(nestedItems).toHaveLength(1)
    expect(findElements(nestedItems[0]!, "shiny-aside-group")).toHaveLength(1)
    expect(findElements(nestedItems[0]!, "strong")).toHaveLength(1)
    expect(findElements(nestedItems[0]!, "blockquote")).toHaveLength(1)
    expect(findElements(nestedItems[0]!, "em")).toHaveLength(1)
  })

  it("preserves Markdown in a deeply nested list-item aside", () => {
    const markdown = [
      "1. Outer item",
      "   - Nested claim.",
      '     <shiny-aside label="Source">',
      "",
      "     **Reason**",
      "     </shiny-aside>",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const asides = findElements(tree, "shiny-aside")
    expect(asides).toHaveLength(1)
    expect(findElements(asides[0]!, "strong")).toHaveLength(1)
    expect(findElements(asides[0]!, "code")).toHaveLength(0)
  })

  it("preserves code inside an aside after a multi-digit list marker", () => {
    const markdown = [
      "10. Claim.",
      '<shiny-aside label="Source">',
      "",
      "    indented code",
      "</shiny-aside>",
      "",
      "11. Next.",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const asides = findElements(tree, "shiny-aside")
    expect(asides).toHaveLength(1)
    expect(findElements(asides[0]!, "code")).toHaveLength(1)
  })

  it("keeps a rich inline opener attached to its list item", () => {
    const markdown = [
      '- Claim.<shiny-aside label="Source">',
      "",
      "**Reason**",
      "</shiny-aside>",
      "",
      "- Next.",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const lists = findElements(tree, "ul")
    const items = lists[0]!.children.filter(
      (child): child is Element =>
        child.type === "element" && child.tagName === "li",
    )
    expect(items).toHaveLength(2)
    expect(findElements(items[0]!, "shiny-aside")).toHaveLength(1)
    expect(findElements(items[0]!, "strong")).toHaveLength(1)
  })

  it("resolves a reference definition outside a list-item aside", () => {
    const markdown = [
      "- Claim.",
      '<shiny-aside label="Source">',
      "",
      "Read [the study][study].",
      "</shiny-aside>",
      "",
      "[study]: https://example.com/study",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const links = findElements(findElements(tree, "shiny-aside")[0]!, "a")
    expect(links).toHaveLength(1)
    expect(links[0]!.properties.href).toBe("https://example.com/study")
  })

  it("makes a definition inside a list-item aside available to the document", () => {
    const markdown = [
      "- Claim.",
      '<shiny-aside label="Source">',
      "",
      "[study]: https://example.com/study",
      "</shiny-aside>",
      "",
      "Outside [the study][study].",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const links = findElements(tree, "a")
    expect(links).toHaveLength(1)
    expect(links[0]!.properties.href).toBe("https://example.com/study")
  })

  it("resolves a footnote definition outside a list-item aside", () => {
    const markdown = [
      "- Claim.",
      '<shiny-aside label="Source">',
      "",
      "Read the note.[^note]",
      "</shiny-aside>",
      "",
      "[^note]: Footnote text.",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const asides = findElements(tree, "shiny-aside")
    expect(
      findElements(asides[0]!, "a").some(
        (link) => link.properties.dataFootnoteRef !== undefined,
      ),
    ).toBe(true)
    expect(
      findElements(tree, "a").some(
        (link) => link.properties.dataFootnoteBackref !== undefined,
      ),
    ).toBe(true)
  })

  it("preserves authored shiny-aside-placeholder elements", () => {
    const markdown = [
      "- Claim.",
      '<shiny-aside label="Source">',
      "",
      "Aside content",
      "</shiny-aside>",
      "",
      '<shiny-aside-placeholder data-shiny-aside-placeholder="0">',
      "Authored content",
      "</shiny-aside-placeholder>",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    expect(findElements(tree, "shiny-aside")).toHaveLength(1)
    expect(findElements(tree, "shiny-aside-placeholder")).toHaveLength(1)
  })

  it("leaves an unmatched closing aside tag on the existing parser path", () => {
    expect(() =>
      parseMarkdown("- Claim.\n</shiny-aside>", markdownProcessor),
    ).not.toThrow()
  })

  it("sanitizes URLs after restoring a protected list-item aside", () => {
    const markdown = [
      "- Claim.",
      '<shiny-aside label="Source" url="javascript:alert(1)">',
      "",
      "**Reason**",
      "",
      "</shiny-aside>",
    ].join("\n")

    const tree = parseMarkdown(markdown, markdownProcessor)
    const asides = findElements(tree, "shiny-aside")
    expect(asides).toHaveLength(1)
    expect(asides[0]!.properties.url).toBe("")
  })
})
