import { visit, SKIP } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

/**
 * Rehype plugin that extracts lazy continuation text from list items.
 *
 * CommonMark treats non-indented text after a list item (without a blank line)
 * as a "lazy continuation line" that belongs to the last list item. The old
 * `marked` parser treated such text as a new paragraph after the list.
 *
 * This plugin restores that behavior: when the last `<li>` in a list ends
 * with a bare text node (starting with `\n`, following an element child),
 * the text is extracted into a new `<p>` sibling placed after the list.
 */
export const rehypeLazyContinuation: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element, index, parent) => {
    if (!parent || index === undefined) return
    if (node.tagName !== "ul" && node.tagName !== "ol") return

    const lastLi = findLastLi(node.children)
    if (!lastLi) return

    const extracted = extractTrailingText(lastLi)
    if (!extracted) return

    const p: Element = {
      type: "element",
      tagName: "p",
      properties: {},
      children: [{ type: "text", value: extracted }],
    }
    parent.children.splice(index + 1, 0, p)
    return [SKIP, index + 1] as const
  })
}

function findLastLi(children: ElementContent[]): Element | null {
  for (let i = children.length - 1; i >= 0; i--) {
    const child = children[i]!
    if (child.type === "element" && child.tagName === "li") return child
  }
  return null
}

/**
 * If the last `<li>` ends with a text node that starts with `\n` (a lazy
 * continuation line), trim it from the `<li>` and return the extracted text.
 */
function extractTrailingText(li: Element): string | null {
  const children = li.children
  if (children.length < 2) return null

  const last = children[children.length - 1]!
  if (last.type !== "text") return null

  // The lazy continuation pattern: text starts with \n after an element
  const nlIndex = last.value.indexOf("\n")
  if (nlIndex === -1) return null

  const before = last.value.substring(0, nlIndex)
  const after = last.value.substring(nlIndex + 1).trim()
  if (!after) return null

  // Verify there's an element sibling before this text node
  const prev = children[children.length - 2]
  if (!prev || prev.type !== "element") return null

  // Trim the text node (keep only the part before the newline)
  if (before.trim()) {
    last.value = before
  } else {
    children.pop()
  }

  return after
}
