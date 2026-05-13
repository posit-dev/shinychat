import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"
import type { Plugin } from "unified"
import { hasSuggestionClass, getTextContent } from "./suggestionHelpers"

/**
 * Rehype plugin that makes suggestion nodes keyboard-focusable at render time.
 *
 * This keeps suggestion accessibility declarative instead of patching the DOM
 * in a React effect after every content update.
 */
export const rehypeAccessibleSuggestions: Plugin<[], Root> = () => (tree) => {
  visit(tree, "element", (node: Element) => {
    const props = node.properties
    if (!props) return

    const hasSuggestion =
      hasSuggestionClass(props.className) || "dataSuggestion" in props
    if (!hasSuggestion) return

    const suggestionText =
      (typeof props.dataSuggestion === "string" && props.dataSuggestion) ||
      getTextContent(node.children)

    if (!("tabIndex" in props)) {
      props.tabIndex = 0
    }

    if (!("role" in props)) {
      props.role = "button"
    }

    if (!("ariaLabel" in props) && suggestionText) {
      props.ariaLabel = `Use chat suggestion: ${suggestionText}`
    }
  })
}
