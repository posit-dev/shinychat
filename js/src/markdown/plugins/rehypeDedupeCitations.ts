import { visit } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"
import { toHtml } from "hast-util-to-html"

function isCitationAside(node: ElementContent): node is Element {
  return (
    node.type === "element" &&
    node.tagName === "shiny-aside" &&
    node.properties != null &&
    "dataCitation" in node.properties
  )
}

// A citation's display is fully a function of (url, rendered body), so this
// key collapses genuine repeats while keeping entries that differ in either.
function citationKey(el: Element): string {
  const url = el.properties?.url
  return `${typeof url === "string" ? url : ""}\n${toHtml(el.children)}`
}

function transform(tree: Root): void {
  visit(tree, "element", (node: Element) => {
    if (node.tagName !== "shiny-aside-group") return
    const seen = new Set<string>()
    node.children = node.children.filter((child) => {
      if (!isCitationAside(child)) return true
      const key = citationKey(child)
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
  })
}

/**
 * Rehype plugin that removes duplicate web-citation asides from each
 * <shiny-aside-group>. Runs AFTER rehypeGroupAsides (which has already
 * container-scoped and collected citation asides into one group per
 * container). Only asides carrying the `data-citation` marker are considered;
 * hand-authored <shiny-aside>s keep the generic block's keep-all behavior.
 */
export const rehypeDedupeCitations: Plugin<[], Root> = () => transform
