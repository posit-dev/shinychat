import { visit, SKIP } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

/** Carrier elements that make up a web-activity burst. */
const WEB_CES = new Set([
  "shiny-web-search",
  "shiny-web-search-results",
  "shiny-web-fetch",
])

function isWebCE(node: ElementContent): node is Element {
  return node.type === "element" && WEB_CES.has((node as Element).tagName)
}

function isWhitespace(node: ElementContent): boolean {
  return node.type === "text" && node.value.trim() === ""
}

function transform(tree: Root): void {
  visit(tree, "element", (node: Element, index, parent) => {
    if (!parent || index === undefined || !isWebCE(node)) return

    // Collect the run of consecutive web CEs, tolerating whitespace text nodes
    // between them. Whitespace is dropped; non-web/non-whitespace ends the run.
    const siblings = parent.children as ElementContent[]
    const collected: Element[] = []
    let last = index
    for (let i = index; i < siblings.length; i++) {
      const c = siblings[i]!
      if (isWebCE(c)) {
        collected.push(c)
        last = i
      } else if (isWhitespace(c)) {
        continue
      } else {
        break
      }
    }

    const wrapper: Element = {
      type: "element",
      tagName: "shiny-web-activity",
      properties: {},
      children: collected,
    }
    siblings.splice(index, last - index + 1, wrapper)
    return [SKIP, index + 1] as const
  })
}

/**
 * Rehype plugin that groups a consecutive run of web-activity custom elements
 * (<shiny-web-search>, <shiny-web-search-results>, <shiny-web-fetch>) into a
 * single <shiny-web-activity> wrapper. Runs after rehypeUnwrapBlockCEs, which
 * promotes these elements to block-level siblings. Any non-whitespace node
 * between elements — prose or another custom element — ends a run, producing
 * one wrapper per burst. A lone web element is wrapped on its own.
 */
export const rehypeGroupWebActivity: Plugin<[], Root> = () => transform
