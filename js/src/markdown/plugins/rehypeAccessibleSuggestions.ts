import { visit } from "unist-util-visit"
import type { Root, Element, RootContent } from "hast"
import type { Plugin } from "unified"

function hasSuggestionClass(className: unknown): boolean {
  if (typeof className === "string") {
    return className.split(/\s+/).includes("suggestion")
  }
  if (Array.isArray(className)) return className.includes("suggestion")
  return false
}

function getTextContent(children: RootContent[] | undefined): string {
  if (!children) return ""

  return children
    .map((child) => {
      if (child.type === "text") return child.value
      if (child.type === "element") return getTextContent(child.children)
      return ""
    })
    .join("")
    .trim()
}

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
