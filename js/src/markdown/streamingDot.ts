import type { Root, Element, ElementContent, RootContent } from "hast"

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
  "p",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "li",
  "code",
])

function hasTextContent(node: ElementContent): boolean {
  if (node.type === "text") return /\S/.test(node.value)
  return false
}

/**
 * Find the innermost element where streaming content is being appended,
 * then insert the streaming dot SVG as a child (mutates the tree).
 */
export function insertStreamingDot(tree: Root): void {
  if (tree.children.length === 0) return

  const target = findInnermostStreamingElement(tree)
  if (target && "children" in target) {
    target.children.push(createDotNode())
  }
}

/**
 * Return a new tree with the streaming dot inserted, without mutating the
 * original. Only the path from root to the insertion point is shallow-copied;
 * all other subtrees are shared by reference. This is O(depth) instead of
 * the O(tree-size) cost of structuredClone.
 */
export function withStreamingDot(tree: Root): Root {
  if (tree.children.length === 0) return tree

  const path = findSpinePath(tree)

  // Shallow-copy each node along the spine, sharing siblings by reference.
  // Start from the root and work down.
  const newRoot: Root = {
    ...tree,
    children: [...tree.children] as RootContent[],
  }

  let parentChildren: (RootContent | ElementContent)[] = newRoot.children
  for (let i = 0; i < path.length; i++) {
    const idx = path[i]!.index
    const original = parentChildren[idx] as Element
    const copy: Element = {
      ...original,
      children: [...original.children],
    }
    parentChildren[idx] = copy as RootContent & ElementContent
    parentChildren = copy.children
  }

  // Append the dot to the deepest copied node's children
  ;(parentChildren as ElementContent[]).push(createDotNode())

  return newRoot
}

/** An entry in the spine path: the index of the child to follow at each level. */
interface SpineEntry {
  index: number
}

/**
 * Find the path from the root to the innermost streaming element.
 * Returns an array of { index } entries, one per level descended.
 * An empty array means the dot should be appended to the root itself.
 */
function findSpinePath(root: Root): SpineEntry[] {
  const path: SpineEntry[] = []
  let current: Root | Element = root
  let depth = 0

  while (depth < 5) {
    depth++
    const children: (RootContent | ElementContent)[] = current.children

    let lastMeaningfulIndex = -1
    let lastMeaningfulChild: ElementContent | null = null
    for (let i = children.length - 1; i >= 0; i--) {
      const child: RootContent | ElementContent = children[i]!
      if (child.type === "doctype") continue
      if (child.type === "element" || hasTextContent(child)) {
        lastMeaningfulIndex = i
        lastMeaningfulChild = child
        break
      }
    }

    if (!lastMeaningfulChild || lastMeaningfulChild.type !== "element") {
      return path
    }

    const tagName = lastMeaningfulChild.tagName

    if (recurseInto.has(tagName)) {
      path.push({ index: lastMeaningfulIndex })
      current = lastMeaningfulChild
      continue
    }

    if (inlineContainers.has(tagName)) {
      path.push({ index: lastMeaningfulIndex })
    }

    return path
  }

  return path
}

// Keep the original for internal use by insertStreamingDot
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
