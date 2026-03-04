import { visit } from "unist-util-visit"
import type { Root, Code, Html } from "mdast"
import type { Plugin } from "unified"

/**
 * Remark plugin that converts code blocks with `{=html}` language
 * to raw HTML nodes, allowing them to pass through as HTML.
 *
 * SECURITY: Must NEVER be used for user-authored content.
 * Only use in the assistant message processor.
 */
export const remarkRawHtml: Plugin<[], Root> = () => (tree) => {
  visit(tree, "code", (node: Code, index, parent) => {
    if (node.lang !== "{=html}" || !parent || index === undefined) return
    const htmlNode: Html = { type: "html", value: node.value }
    parent.children.splice(index, 1, htmlNode)
  })
}
