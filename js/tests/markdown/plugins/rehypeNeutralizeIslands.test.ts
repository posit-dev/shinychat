import { describe, expect, it } from "vitest"
import { unified } from "unified"
import remarkParse from "remark-parse"
import remarkGfm from "remark-gfm"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import rehypeStringify from "rehype-stringify"
import {
  disguiseIslandsHtml,
  rehypeDisguiseIslands,
  rehypeNeutralizeIslands,
} from "../../../src/markdown/plugins/rehypeNeutralizeIslands"
import {
  rehypeRewriteAsideFromTemplate,
  rehypeRewriteAsideToTemplate,
} from "../../../src/markdown/plugins/rewriteAsideTemplate"

function processMarkdown(markdown: string): string {
  return String(
    unified()
      .use(remarkParse)
      .use(remarkGfm)
      .use(remarkRehype, { allowDangerousHtml: true })
      .use(rehypeRewriteAsideToTemplate)
      .use(rehypeDisguiseIslands)
      .use(rehypeRaw)
      .use(rehypeNeutralizeIslands)
      .use(rehypeRewriteAsideFromTemplate)
      .use(rehypeStringify)
      .processSync(markdown),
  )
}

describe("raw-HTML island neutralizing (spoof guard)", () => {
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

  it("neutralizes block children and preserves trailing markdown", () => {
    // The disguise→template round-trip is what keeps parse5 from hoisting
    // the block-level <div> out of the forged tag before the guard runs.
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

  it("neutralizes an island nested in an aside template fragment", () => {
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
      disguiseIslandsHtml(
        "İstanbul <shiny-chat-raw-html>x</shiny-chat-raw-html>",
      ),
    ).toBe(
      'İstanbul <template data-reserved-island="shiny-chat-raw-html">x</template>',
    )
  })
})
