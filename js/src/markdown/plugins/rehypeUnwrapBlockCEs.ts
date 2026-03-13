import { visit, SKIP } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

/**
 * Set of custom element tag names that are block-level and must not appear
 * inside <p> elements. When found inside a <p>, the <p> is split: content
 * before the CE becomes one <p>, the CE is promoted to a sibling, and content
 * after becomes another <p>.
 */
const blockCEs = new Set([
  "shiny-tool-request",
  "shiny-tool-result",
  "shinychat-html",
])

function isBlockCE(node: ElementContent): node is Element {
  return node.type === "element" && blockCEs.has((node as Element).tagName)
}

function hasContent(nodes: ElementContent[]): boolean {
  return nodes.some((n) => {
    if (n.type === "text") return n.value.trim().length > 0
    return true
  })
}

/**
 * Transformer that unwraps block-level custom elements from <p> parents.
 * Extracted so it can be called recursively to handle multiple CEs in one <p>.
 */
function transform(tree: Root): void {
  visit(tree, "element", (node: Element, index, parent) => {
    if (node.tagName !== "p" || !parent || index === undefined) return

    // Check if any child is a block-level custom element
    const blockIndex = node.children.findIndex(isBlockCE)
    if (blockIndex === -1) return

    // Split: [before, blockCE, after] -> [<p>before</p>, blockCE, <p>after</p>]
    const before = node.children.slice(0, blockIndex)
    const blockEl = node.children[blockIndex]!
    const after = node.children.slice(blockIndex + 1)

    const replacements: ElementContent[] = []

    // Only create a <p> for "before" if it has meaningful content
    if (before.length > 0 && hasContent(before)) {
      replacements.push({ ...node, children: before })
    }

    replacements.push(blockEl)

    // Recursively handle "after" — it may contain more block CEs
    if (after.length > 0 && hasContent(after)) {
      const afterP: Element = { ...node, children: after }
      // Wrap in a temporary root so we can recurse
      const tempRoot: Root = { type: "root", children: [afterP] }
      transform(tempRoot)
      replacements.push(...(tempRoot.children as ElementContent[]))
    }

    parent.children.splice(index, 1, ...replacements)
    return [SKIP, index] as const
  })
}

/**
 * Rehype plugin that unwraps block-level custom elements from <p> parents.
 *
 * Markdown parsers wrap inline HTML in <p> tags. When the "inline" HTML is
 * actually a block-level custom element (like <shiny-tool-request>), this
 * produces invalid HTML (<p> cannot contain <div>). This plugin splits the
 * <p> and promotes the custom element to a sibling.
 */
export const rehypeUnwrapBlockCEs: Plugin<[], Root> = () => transform
