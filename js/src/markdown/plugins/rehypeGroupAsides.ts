import { visit, SKIP } from "unist-util-visit"
import type { Root, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

function isAside(node: ElementContent): node is Element {
  return node.type === "element" && node.tagName === "shiny-aside"
}

function isLabeled(aside: Element): boolean {
  const label = aside.properties?.label
  return typeof label === "string" && label !== ""
}

function hasNestedParagraph(node: Element): boolean {
  return node.children.some((c) => c.type === "element" && c.tagName === "p")
}

/**
 * <p> always holds inline content directly. A tight list's <li> does too; a
 * loose list wraps each <li>'s content in its own nested <p>, which is
 * handled by that inner match instead (skip the <li> itself there to avoid
 * double-collecting the same asides).
 */
function isAsideContainer(node: Element): boolean {
  if (node.tagName === "p") return true
  if (node.tagName !== "li") return false
  return !hasNestedParagraph(node)
}

function collectAndRemoveAsides(container: Element): Element[] {
  const collected: Element[] = []
  visit(container, "element", (node, index, parent) => {
    // A nested <li> is its own aside container, handled by its own call
    // from the outer `transform` visit — don't let an ancestor's pass steal
    // its asides.
    if (node !== container && node.tagName === "li") return SKIP
    if (!isAside(node) || !parent || index === undefined) return
    collected.push(node)
    ;(parent.children as ElementContent[]).splice(index, 1)
    return [SKIP, index] as const
  })
  return collected
}

function makeGroup(children: Element[]): Element {
  return {
    type: "element",
    tagName: "shiny-aside-group",
    properties: {},
    children,
  }
}

function transform(tree: Root): void {
  let asideIndex = 0
  visit(tree, "element", (node: Element) => {
    if (!isAsideContainer(node)) return
    const found = collectAndRemoveAsides(node)
    if (found.length === 0) return

    const labeled = found.filter(isLabeled)
    const labeledGroup = labeled.length > 0 ? makeGroup(labeled) : null
    let labeledGroupPlaced = false
    const groups: Element[] = []
    for (const aside of found) {
      if (isLabeled(aside)) {
        if (!labeledGroupPlaced) {
          groups.push(labeledGroup!)
          labeledGroupPlaced = true
        }
        continue
      }
      asideIndex += 1
      aside.properties = { ...aside.properties, index: asideIndex }
      groups.push(makeGroup([aside]))
    }
    node.children.push(...groups)
  })
}

/**
 * Rehype plugin that processes every <shiny-aside> found anywhere within
 * a paragraph or tight list item. Asides carrying a `label` collapse into
 * a single trailing <shiny-aside-group>, keeping every one in document
 * order (each stays a distinct popover entry — the pill decides whether to
 * show an overflow count). Label-less asides never bundle with anything:
 * each becomes its own single-entry <shiny-aside-group>, stamped with
 * `index`, a counter that runs across the *entire* tree passed to this
 * plugin (i.e. the whole message, since each message is parsed
 * independently) so pills can show a stable, message-scoped aside number
 * instead of a per-container count.
 */
export const rehypeGroupAsides: Plugin<[], Root> = () => transform
