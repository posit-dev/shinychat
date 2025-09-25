/**
 * Find the innermost element where streaming is happening, i.e. where the
 * streaming is appending new content.
 */
const findInnermostStreamingElement = (element: Element): Element => {
  let current = element
  let depth = 0

  while (depth < 5) {
    depth++
    const children = current.childNodes

    let lastMeaningfulChild: Node | null = null

    // Find last meaningful child
    for (let i = children.length - 1; i >= 0; i--) {
      const child = children[i]
      if (!child) break
      if (
        child.nodeType === Node.ELEMENT_NODE ||
        (child.nodeType === Node.TEXT_NODE && hasText(child as Text))
      ) {
        lastMeaningfulChild = child
        break
      }
    }

    if (!lastMeaningfulChild || !(lastMeaningfulChild instanceof Element)) {
      // If no meaningful child, or last child is a text node, streaming
      // is happening the `current` element.
      return current
    }

    const tagName = lastMeaningfulChild.tagName.toLowerCase()

    if (CONTAINERS_RECURSE.has(tagName)) {
      current = lastMeaningfulChild
      continue // Keep drilling down to find innermost streaming element
    }

    return CONTAINERS_INLINE.has(tagName) ? lastMeaningfulChild : current
  }

  return current
}

const hasText = (node: Text): boolean => /\S/.test(node.textContent || "")

// We go into these elements to find the innermost streaming element
const CONTAINERS_RECURSE = new Set(["p", "div", "pre", "ul", "ol"])
// We can put the dot in these kinds of containers
const CONTAINERS_INLINE = new Set([
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

export { findInnermostStreamingElement }
