import { visit } from "unist-util-visit"
import { toHtml } from "hast-util-to-html"
import type { Plugin } from "unified"
import type { Element, Root } from "hast"

export const HTML_ISLAND_RAW_HTML = "rawHtml"

declare module "hast" {
  interface ElementData {
    [HTML_ISLAND_RAW_HTML]?: string
  }
}

export const rehypeSnapshotHtmlIslands: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "shinychat-raw-html") return

    const serialized = toHtml(node.children ?? [])
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(node.data ??= {} as any)[HTML_ISLAND_RAW_HTML] = serialized
  })
}
