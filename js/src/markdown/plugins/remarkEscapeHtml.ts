import { visit, SKIP } from "unist-util-visit"
import type { Root, Html, Text } from "mdast"
import type { Plugin } from "unified"

/**
 * Remark plugin that converts raw HTML nodes to plain text nodes.
 * This causes HTML tags to be displayed literally (escaped) rather
 * than interpreted as HTML. Used for user messages (semi-markdown).
 */
export const remarkEscapeHtml: Plugin<[], Root> = () => (tree) => {
  visit(tree, "html", (node: Html, index, parent) => {
    if (!parent || index === undefined) return
    const textNode: Text = { type: "text", value: node.value }
    parent.children.splice(index, 1, textNode)
    return [SKIP, index]
  })
}
