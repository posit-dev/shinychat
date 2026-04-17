import { describe, it, expect } from "vitest"
import { unified } from "unified"
import { visit } from "unist-util-visit"
import remarkParse from "remark-parse"
import remarkRehype from "remark-rehype"
import rehypeRaw from "rehype-raw"
import { rehypeAccessibleSuggestions } from "../../../src/markdown/plugins/rehypeAccessibleSuggestions"
import {
  rehypeSnapshotHtmlIslands,
  HTML_ISLAND_RAW_HTML,
} from "../../../src/markdown/plugins/rehypeSnapshotHtmlIslands"
import rehypeStringify from "rehype-stringify"
import type { Element } from "hast"

function snapshotFromMarkdown(md: string): string | undefined {
  let snapshot: string | undefined

  unified()
    .use(remarkParse)
    .use(remarkRehype, { allowDangerousHtml: true })
    .use(rehypeRaw)
    .use(rehypeSnapshotHtmlIslands)
    .use(rehypeAccessibleSuggestions)
    .use(() => (tree) => {
      visit(tree, "element", (node: Element) => {
        if (node.tagName === "shinychat-raw-html") {
          snapshot = node.data?.[HTML_ISLAND_RAW_HTML] as string | undefined
        }
      })
    })
    .use(rehypeStringify)
    .processSync(md)

  return snapshot
}

describe("rehypeSnapshotHtmlIslands", () => {
  it("captures the original inner HTML before other rehype plugins mutate it", () => {
    const inner = "<button class='suggestion'>Use hint</button>"
    const md = `<shinychat-raw-html>${inner}</shinychat-raw-html>`
    const normalizedInner = '<button class="suggestion">Use hint</button>'
    expect(snapshotFromMarkdown(md)).toBe(normalizedInner)
  })
})
