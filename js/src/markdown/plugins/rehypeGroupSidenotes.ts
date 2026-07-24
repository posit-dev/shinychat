import { visit, SKIP } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

function isSidenote(node: ElementContent): node is Element {
  return node.type === "element" && node.tagName === "shiny-sidenote"
}

function isLabeled(sidenote: Element): boolean {
  const label = sidenote.properties?.label
  return typeof label === "string" && label !== ""
}

function hasNestedParagraph(node: Element): boolean {
  return node.children.some((c) => c.type === "element" && c.tagName === "p")
}

/**
 * <p> always holds inline content directly. A tight list's <li> does too; a
 * loose list wraps each <li>'s content in its own nested <p>, which is
 * handled by that inner match instead (skip the <li> itself there to avoid
 * double-collecting the same sidenotes).
 */
function isSidenoteContainer(node: Element): boolean {
  if (node.tagName === "p") return true
  if (node.tagName !== "li") return false
  return !hasNestedParagraph(node)
}

function collectAndRemoveSidenotes(container: Element): Element[] {
  const collected: Element[] = []
  visit(container, "element", (node, index, parent) => {
    // A nested <li> is its own sidenote container, handled by its own call
    // from the outer `transform` visit — don't let an ancestor's pass steal
    // its sidenotes.
    if (node !== container && node.tagName === "li") return SKIP
    if (!isSidenote(node) || !parent || index === undefined) return
    collected.push(node)
    ;(parent.children as ElementContent[]).splice(index, 1)
    return [SKIP, index] as const
  })
  return collected
}

function dedupeByLabel(labeledSidenotes: Element[]): Element[] {
  const seenLabels = new Set<string>()
  const kept: Element[] = []
  for (const sidenote of labeledSidenotes) {
    const label = sidenote.properties!.label as string
    if (seenLabels.has(label)) continue
    seenLabels.add(label)
    kept.push(sidenote)
  }
  return kept
}

function makeGroup(children: Element[]): Element {
  return {
    type: "element",
    tagName: "shiny-sidenote-group",
    properties: {},
    children,
  }
}

function transform(tree: Root): void {
  let sidenoteIndex = 0
  visit(tree, "element", (node: Element) => {
    if (!isSidenoteContainer(node)) return
    const found = collectAndRemoveSidenotes(node)
    if (found.length === 0) return

    const labeled = found.filter(isLabeled)
    const labeledGroup =
      labeled.length > 0 ? makeGroup(dedupeByLabel(labeled)) : null
    let labeledGroupPlaced = false
    const groups: Element[] = []
    for (const sidenote of found) {
      if (isLabeled(sidenote)) {
        if (!labeledGroupPlaced) {
          groups.push(labeledGroup!)
          labeledGroupPlaced = true
        }
        continue
      }
      sidenoteIndex += 1
      sidenote.properties = { ...sidenote.properties, index: sidenoteIndex }
      groups.push(makeGroup([sidenote]))
    }
    node.children.push(...groups)
  })
}

/**
 * Rehype plugin that processes every <shiny-sidenote> found anywhere within
 * a paragraph or tight list item. Sidenotes carrying a `label` collapse into
 * a single trailing <shiny-sidenote-group>, deduped by label (first
 * occurrence wins) — unchanged from before. Label-less sidenotes never
 * bundle with anything: each becomes its own single-entry
 * <shiny-sidenote-group>, stamped with `index`, a counter that runs across
 * the *entire* tree passed to this plugin (i.e. the whole message, since
 * each message is parsed independently) so pills can show a stable,
 * message-scoped sidenote number instead of a per-container count.
 */
export const rehypeGroupSidenotes: Plugin<[], Root> = () => transform
