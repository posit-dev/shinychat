import { visit } from "unist-util-visit"
import type { Root, Element } from "hast"

/**
 * URL attributes that should be sanitized, mapped to the elements they apply to.
 * null means the attribute applies to any element.
 * Ported from react-markdown's defaultUrlTransform.
 */
const urlAttributes: Record<string, string[] | null> = {
  href: ["a", "area", "base", "link"],
  src: ["audio", "embed", "iframe", "img", "input", "script", "source", "track", "video"],
  poster: ["video"],
  action: ["form"],
  formAction: ["button", "input"],
  cite: ["blockquote", "del", "ins", "q"],
}

const safeProtocol = /^(https?|ircs?|mailto|xmpp)$/i

function isSafeUrl(value: string): boolean {
  const colon = value.indexOf(":")
  const questionMark = value.indexOf("?")
  const numberSign = value.indexOf("#")
  const slash = value.indexOf("/")

  if (
    colon === -1 ||
    (slash !== -1 && colon > slash) ||
    (questionMark !== -1 && colon > questionMark) ||
    (numberSign !== -1 && colon > numberSign) ||
    safeProtocol.test(value.slice(0, colon))
  ) {
    return true
  }

  return false
}

/**
 * Sanitize URLs in a hast tree. Removes unsafe URLs (javascript:, data:, etc.)
 * from URL-bearing attributes. Call after all rehype plugins, before toJsxRuntime.
 */
export function sanitizeUrls(tree: Root): void {
  visit(tree, "element", (node: Element) => {
    for (const [attr, elements] of Object.entries(urlAttributes)) {
      if (elements !== null && !elements.includes(node.tagName)) continue
      const value = node.properties?.[attr]
      if (typeof value === "string" && !isSafeUrl(value)) {
        node.properties[attr] = ""
      }
    }
  })
}
