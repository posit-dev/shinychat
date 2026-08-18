import type { Element, ElementContent, Root, RootContent } from "hast"
import type { Plugin } from "unified"

type AttachmentParent = Root | Element
type AttachmentChild = RootContent | ElementContent

export const rehypeAttachAsidesToPreviousParagraph: Plugin<[], Root> = () =>
  attachAsides

function attachAsides(tree: Root): void {
  attachWithin(tree)
}

function attachWithin(parent: AttachmentParent): void {
  const children = parent.children
  let previousParagraph: Element | null = null
  let index = 0

  while (index < children.length) {
    const child = children[index]!

    if (isWhitespace(child)) {
      index += 1
      continue
    }

    const standaloneAsides = asidesInStandaloneParagraph(child)
    if (standaloneAsides) {
      if (previousParagraph) {
        previousParagraph.children.push(...standaloneAsides)
        children.splice(index, 1)
        continue
      }
      previousParagraph = null
      index += 1
      continue
    }

    if (isParagraph(child)) {
      previousParagraph = child
      index += 1
      continue
    }

    if (previousParagraph && isAside(child)) {
      previousParagraph.children.push(child)
      children.splice(index, 1)
      continue
    }

    previousParagraph = null
    index += 1
  }

  for (const child of parent.children) {
    if (child.type === "element" && child.tagName !== "shiny-aside") {
      attachWithin(child)
    }
  }
}

function asidesInStandaloneParagraph(node: AttachmentChild): Element[] | null {
  if (!isParagraph(node)) return null

  const asides: Element[] = []
  for (const child of node.children) {
    if (isAside(child)) {
      asides.push(child)
    } else if (!isWhitespace(child)) {
      return null
    }
  }
  return asides.length > 0 ? asides : null
}

function isParagraph(node: AttachmentChild): node is Element {
  return node.type === "element" && node.tagName === "p"
}

function isAside(node: AttachmentChild): node is Element {
  return node.type === "element" && node.tagName === "shiny-aside"
}

function isWhitespace(node: AttachmentChild): boolean {
  return node.type === "text" && node.value.trim() === ""
}
