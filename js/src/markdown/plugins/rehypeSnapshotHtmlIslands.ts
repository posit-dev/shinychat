import { visit } from "unist-util-visit"
import { toHtml } from "hast-util-to-html"
import type { Plugin } from "unified"
import type { Element, Root } from "hast"

export const HTML_ISLAND_RAW_HTML = "rawHtml"

export const rehypeSnapshotHtmlIslands: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "shinychat-raw-html") return

    const serialized = toHtml(node.children ?? [])
    node.data = {
      ...node.data,
      [HTML_ISLAND_RAW_HTML]: serialized,
    }
  })
}
