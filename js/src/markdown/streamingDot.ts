import type { Root, Element, ElementContent } from "hast"

const SVG_DOT_CLASS = "markdown-stream-dot"

/**
 * Creates a hast element node representing the streaming dot SVG.
 */
function createDotNode(): Element {
  return {
    type: "element",
    tagName: "svg",
    properties: {
      width: 12,
      height: 12,
      xmlns: "http://www.w3.org/2000/svg",
      className: [SVG_DOT_CLASS],
      style: "margin-left:.25em;margin-top:-.25em",
    },
    children: [
      {
        type: "element",
        tagName: "circle",
        properties: { cx: 6, cy: 6, r: 6 },
        children: [],
      },
    ],
  }
}

const recurseInto = new Set(["p", "div", "pre", "ul", "ol"])
const inlineContainers = new Set([
  "p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "code",
])

function hasTextContent(node: ElementContent): boolean {
  if (node.type === "text") return /\S/.test(node.value)
  return false
}

/**
 * Find the innermost element where streaming content is being appended,
 * then insert the streaming dot SVG as a child.
 *
 * Mirrors the algorithm in the current Lit `appendStreamingDot` method.
 */
export function insertStreamingDot(tree: Root): void {
  // Don't insert if tree has no meaningful content
  if (tree.children.length === 0) return

  const target = findInnermostStreamingElement(tree)
  if (target && "children" in target) {
    target.children.push(createDotNode())
  }
}

function findInnermostStreamingElement(
  element: Root | Element,
): Root | Element {
  let current: Root | Element = element
  let depth = 0

  while (depth < 5) {
    depth++
    const children = current.children

    let lastMeaningfulChild: ElementContent | null = null
    for (let i = children.length - 1; i >= 0; i--) {
      const child = children[i]!
      if (child.type === "doctype") continue
      if (child.type === "element" || hasTextContent(child)) {
        lastMeaningfulChild = child
        break
      }
    }

    if (!lastMeaningfulChild || lastMeaningfulChild.type !== "element") {
      return current
    }

    const tagName = lastMeaningfulChild.tagName

    if (recurseInto.has(tagName)) {
      current = lastMeaningfulChild
      continue
    }

    return inlineContainers.has(tagName) ? lastMeaningfulChild : current
  }

  return current
}
