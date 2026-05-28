import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"

/**
 * Rehype plugin that marks navigating links for click interception.
 * Must run AFTER rehype-sanitize (or the attributes get stripped).
 */
export const rehypeExternalLinks: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "a") return
    const href = node.properties?.href
    if (typeof href !== "string") return
    if (href.startsWith("#")) return
    if (/^[a-z][a-z0-9+.-]*:/i.test(href) && !/^https?:/i.test(href)) return

    node.properties = {
      ...node.properties,
      dataShinychatLink: "",
      target: "_blank",
      rel: "noopener noreferrer",
    }
  })
}
