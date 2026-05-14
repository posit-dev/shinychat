import type { Element, ElementContent, RootContent } from "hast"

/**
 * Attribute name used to mark a pending (mid-stream) suggestion list.
 * Shared between rehypeSuggestionCards and streamingDot so the literal
 * string never has to be duplicated.
 */
export const SUGGESTION_PENDING_ATTR = "dataPending"

export function hasSuggestionClass(className: unknown): boolean {
  if (typeof className === "string") {
    return className.split(/\s+/).includes("suggestion")
  }
  if (Array.isArray(className)) return className.includes("suggestion")
  return false
}

export function getTextContent(children: RootContent[] | undefined): string {
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

export function isSuggestionElement(node: ElementContent): node is Element {
  if (node.type !== "element") return false
  const props = node.properties
  if (!props) return false
  return hasSuggestionClass(props.className) || "dataSuggestion" in props
}
