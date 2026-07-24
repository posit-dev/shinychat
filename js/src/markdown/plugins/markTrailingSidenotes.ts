import type { Root, Element, ElementContent, RootContent } from "hast"
import type { Plugin } from "unified"

/**
 * Attribute marking a sidenote group whose surrounding block is still being
 * streamed. While present, `<SidenoteGroup>` renders nothing so the pill does
 * not flash into view (and jitter as text streams past it) before its position
 * is settled. `finalizePendingSidenotes` clears it at end of stream.
 */
export const SIDENOTE_PENDING_ATTR = "dataPending"

const GROUP_TAG = "shiny-sidenote-group"

function isPendingGroup(el: Element): boolean {
  return (
    el.tagName === GROUP_TAG &&
    el.properties != null &&
    SIDENOTE_PENDING_ATTR in el.properties
  )
}

function lastElementChild(node: Root | Element): Element | null {
  const children = node.children as (RootContent | ElementContent)[]
  for (let i = children.length - 1; i >= 0; i--) {
    const child = children[i]
    if (child && child.type === "element") return child
  }
  return null
}

function markGroupChildrenPending(container: Root | Element): void {
  for (const child of container.children) {
    if (child.type === "element" && child.tagName === GROUP_TAG) {
      child.properties = { ...child.properties, [SIDENOTE_PENDING_ATTR]: "" }
    }
  }
}

/**
 * Mark every sidenote group inside the still-open trailing block as pending.
 *
 * During streaming the growing block is always the deepest one reached by
 * following the last element child at each level. `rehypeGroupSidenotes`
 * appends each group as the last child of its container, so encountering a
 * group along that descent means its parent is the open block — its sidenotes
 * are not yet fixed in place. Everything earlier in document order has been
 * settled by a following block and is left visible.
 */
export const rehypeMarkTrailingSidenotes: Plugin<[], Root> = () => (tree) => {
  let current: Root | Element = tree
  while (true) {
    const lastEl = lastElementChild(current)
    if (!lastEl) return
    if (lastEl.tagName === GROUP_TAG) {
      markGroupChildrenPending(current)
      return
    }
    current = lastEl
  }
}

/**
 * Clear pending markers from all sidenote groups, returning a new tree only if
 * something changed (identity otherwise). Called from `hastToReact` when
 * streaming has ended; mirrors the path-copy strategy of the suggestion
 * finalizer so the cached Stage-1 HAST is never mutated.
 */
export function finalizePendingSidenotes(tree: Root): Root {
  const children = stripChildren(tree.children)
  return children ? { ...tree, children } : tree
}

// Returns a new children array if any descendant changed, otherwise null.
function stripChildren<T extends RootContent | ElementContent>(
  children: T[],
): T[] | null {
  let changed = false
  const out = children.map((child) => {
    if (child.type !== "element") return child
    const stripped = stripElement(child)
    if (stripped !== child) changed = true
    return stripped as T
  })
  return changed ? out : null
}

function stripElement(el: Element): Element {
  const pending = isPendingGroup(el)
  const newChildren = stripChildren(el.children)
  if (!pending && !newChildren) return el
  const properties = { ...el.properties }
  if (pending) delete properties[SIDENOTE_PENDING_ATTR]
  return { ...el, properties, children: newChildren ?? el.children }
}
