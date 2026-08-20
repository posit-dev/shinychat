import { visit, SKIP } from "unist-util-visit"
import type { Root, RootContent, Element, ElementContent } from "hast"
import type { Plugin } from "unified"

function isAside(node: RootContent | ElementContent): node is Element {
  return node.type === "element" && node.tagName === "shiny-aside"
}

function isLabeled(aside: Element): boolean {
  const label = aside.properties?.label
  return (
    (typeof label === "string" && label !== "") ||
    aside.properties?.dataCitation != null
  )
}

function usesCompactDisplay(aside: Element): boolean {
  return aside.properties?.display === "compact"
}

function usesIdentityMarker(aside: Element): boolean {
  return isLabeled(aside) && !usesCompactDisplay(aside)
}

function usesCountMarker(aside: Element): boolean {
  return !isLabeled(aside) || usesCompactDisplay(aside)
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

function collectAndRemoveRootAsides(root: Root): Element[] {
  const collected = root.children.filter(isAside)
  if (collected.length === 0) return []
  root.children = root.children.filter((child) => !isAside(child))
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

function makeGroups(found: Element[]): Element[] {
  const identityAsides = found.filter(usesIdentityMarker)
  const identityGroup =
    identityAsides.length > 0 ? makeGroup(identityAsides) : null
  const compactAsides = found.filter(usesCompactDisplay)
  const compactGroup =
    compactAsides.length > 0 ? makeGroup(compactAsides) : null
  let identityGroupPlaced = false
  let compactGroupPlaced = false
  const groups: Element[] = []

  for (const aside of found) {
    if (usesIdentityMarker(aside)) {
      if (!identityGroupPlaced) {
        groups.push(identityGroup!)
        identityGroupPlaced = true
      }
    } else if (usesCompactDisplay(aside)) {
      if (!compactGroupPlaced) {
        groups.push(compactGroup!)
        compactGroupPlaced = true
      }
    } else {
      groups.push(makeGroup([aside]))
    }
  }
  return groups
}

function assignCountMarkerIndexes(tree: Root): void {
  let asideIndex = 0
  visit(tree, "element", (node: Element) => {
    if (!isAside(node) || !usesCountMarker(node)) return
    asideIndex += 1
    node.properties = { ...node.properties, index: asideIndex }
  })
}

function transform(tree: Root): void {
  assignCountMarkerIndexes(tree)

  visit(tree, "element", (node: Element) => {
    if (!isAsideContainer(node)) return
    const found = collectAndRemoveAsides(node)
    if (found.length === 0) return
    trimTrailingAsideBreaks(node.children)
    node.children.push(...makeGroups(found))
  })

  const rootGroups = makeGroups(collectAndRemoveRootAsides(tree))
  tree.children.push(...rootGroups)
}

function trimTrailingAsideBreaks(children: ElementContent[]): void {
  while (children.length > 0) {
    const last = children[children.length - 1]!
    if (last.type === "element" && last.tagName === "br") {
      children.pop()
      continue
    }
    if (last.type !== "text") return

    const value = last.value.trimEnd()
    if (value) {
      last.value = value
      return
    }
    children.pop()
  }
}

/**
 * Rehype plugin that processes every <shiny-aside> found anywhere within
 * a paragraph or tight list item. Asides carrying a `label` and native web
 * citations collapse into a single trailing <shiny-aside-group>, unless they
 * explicitly request `display="compact"`. Compact labeled asides collapse into
 * their own group per container, while label-less asides each become a
 * single-entry group. Both are stamped with `index`, a counter that runs across
 * the *entire* tree passed to this plugin (i.e. the whole message, since each
 * message is parsed independently) so pills can show stable, message-scoped
 * aside numbers instead of per-container counts.
 */
export const rehypeGroupAsides: Plugin<[], Root> = () => transform
