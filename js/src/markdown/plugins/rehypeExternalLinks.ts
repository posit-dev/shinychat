import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"

/**
 * Rehype plugin that adds external link attributes to absolute URLs.
 * Must run AFTER rehype-sanitize (or the attributes get stripped).
 */
export const rehypeExternalLinks: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "a") return
    const href = node.properties?.href
    if (typeof href !== "string") return
    if (/^(https?:)?\/\//.test(href)) {
      node.properties = {
        ...node.properties,
        dataExternalLink: "",
        target: "_blank",
        rel: "noopener noreferrer",
      }
    }
  })
}
