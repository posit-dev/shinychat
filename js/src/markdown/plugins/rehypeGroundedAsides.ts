import type { Element, ElementContent, Root, Text } from "hast"
import type { Plugin } from "unified"
import { visit } from "unist-util-visit"

interface TextSegment {
  node: Text
  start: number
  end: number
}

interface AsideMarker {
  node: Element
  offset: number
  groundedSpan: string
}

interface GroundedRange {
  start: number
  end: number
  id: string
}

function stringProperty(node: Element, name: string): string | undefined {
  const value = node.properties?.[name]
  return typeof value === "string" && value !== "" ? value : undefined
}

function hasNestedParagraph(node: Element): boolean {
  return node.children.some(
    (child) => child.type === "element" && child.tagName === "p",
  )
}

function isGroundingContainer(node: Element): boolean {
  if (node.tagName === "p") return true
  return node.tagName === "li" && !hasNestedParagraph(node)
}

function collectGroundingContent(container: Element): {
  text: string
  segments: TextSegment[]
  asides: AsideMarker[]
} {
  let text = ""
  const segments: TextSegment[] = []
  const asides: AsideMarker[] = []

  const collect = (node: ElementContent): void => {
    if (node.type === "text") {
      const start = text.length
      text += node.value
      segments.push({ node, start, end: text.length })
      return
    }
    if (node.type !== "element") return
    if (node.tagName === "shiny-aside") {
      const groundedSpan = stringProperty(node, "grounded-span")
      if (groundedSpan) asides.push({ node, offset: text.length, groundedSpan })
      return
    }
    if (node.tagName === "p" || node.tagName === "li") return
    for (const child of node.children) collect(child)
  }

  for (const child of container.children) collect(child)
  return { text, segments, asides }
}

function groundedTextNodes(
  segment: TextSegment,
  ranges: GroundedRange[],
): ElementContent[] {
  const overlapping = ranges.filter(
    (range) => range.start < segment.end && range.end > segment.start,
  )
  if (overlapping.length === 0) return [segment.node]

  const boundaries = new Set([segment.start, segment.end])
  for (const range of overlapping) {
    boundaries.add(Math.max(segment.start, range.start))
    boundaries.add(Math.min(segment.end, range.end))
  }
  const sorted = [...boundaries].sort((a, b) => a - b)
  const result: ElementContent[] = []

  for (let index = 0; index < sorted.length - 1; index += 1) {
    const start = sorted[index]!
    const end = sorted[index + 1]!
    const value = segment.node.value.slice(
      start - segment.start,
      end - segment.start,
    )
    const ids = overlapping
      .filter((range) => range.start <= start && range.end >= end)
      .map((range) => range.id)
    const textNode: Text = { type: "text", value }
    if (ids.length === 0) {
      result.push(textNode)
    } else {
      result.push({
        type: "element",
        tagName: "span",
        properties: {
          className: ["shiny-aside-grounded"],
          dataAsideGrounding: ids.join(" "),
        },
        children: [textNode],
      })
    }
  }

  return result
}

function rewriteGroundedText(
  node: Element,
  segments: Map<Text, TextSegment>,
  ranges: GroundedRange[],
): void {
  node.children = node.children.flatMap((child) => {
    if (child.type === "text") {
      const segment = segments.get(child)
      return segment ? groundedTextNodes(segment, ranges) : child
    }
    if (child.type === "element" && child.tagName !== "shiny-aside") {
      rewriteGroundedText(child, segments, ranges)
    }
    return child
  })
}

function groundAsides(container: Element, nextId: () => string): void {
  const { text, segments, asides } = collectGroundingContent(container)
  const ranges: GroundedRange[] = []

  for (const aside of asides) {
    const start = text.slice(0, aside.offset).lastIndexOf(aside.groundedSpan)
    if (start === -1) continue

    const id = nextId()
    aside.node.properties = {
      ...aside.node.properties,
      dataGroundingId: id,
    }
    ranges.push({
      start,
      end: start + aside.groundedSpan.length,
      id,
    })
  }

  if (ranges.length === 0) return
  rewriteGroundedText(
    container,
    new Map(segments.map((segment) => [segment.node, segment])),
    ranges,
  )
}

function transform(tree: Root): void {
  let groundingIndex = 0
  const nextId = () => {
    groundingIndex += 1
    return `aside-grounding-${groundingIndex}`
  }

  visit(tree, "element", (node: Element) => {
    if (isGroundingContainer(node)) groundAsides(node, nextId)
  })
}

/**
 * Connect an aside's grounded span to the most recent exact preceding match
 * in the same paragraph or tight list item.
 */
export const rehypeGroundedAsides: Plugin<[], Root> = () => transform
