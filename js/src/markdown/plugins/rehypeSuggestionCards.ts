import type { Root, Element, ElementContent, RootContent } from "hast"
import type { Plugin } from "unified"
import {
  SUGGESTION_PENDING_ATTR,
  hasSuggestionClass,
  getTextContent,
  isSuggestionElement,
} from "./suggestionHelpers"

function isNonWhitespaceText(node: RootContent): boolean {
  return node.type === "text" && node.value.trim() !== ""
}

function significantChildren(children: ElementContent[]): ElementContent[] {
  return children.filter(
    (child) =>
      child.type === "element" ||
      (child.type === "text" && child.value.trim() !== ""),
  )
}

function isQualifyingList(node: Element): boolean {
  const kids = node.children as ElementContent[]

  if (kids.some(isNonWhitespaceText)) return false

  const elements = kids.filter((c) => c.type === "element") as Element[]

  if (elements.length === 0) return false

  for (const child of elements) {
    if (child.tagName !== "li") return false

    const liKids = child.children as ElementContent[]
    if (liKids.some(isNonWhitespaceText)) return false

    const liElements = significantChildren(liKids).filter(
      (c) => c.type === "element",
    ) as Element[]

    if (liElements.length !== 1) return false
    const onlyEl = liElements[0]
    if (!onlyEl || !isSuggestionElement(onlyEl)) return false
  }

  return true
}

function appendClass(
  className: unknown,
  ...additions: string[]
): Array<string | number> {
  let existing: Array<string | number>
  if (Array.isArray(className)) {
    existing = [...className] as Array<string | number>
  } else if (typeof className === "string" && className.trim() !== "") {
    existing = className.split(/\s+/).filter(Boolean)
  } else {
    existing = []
  }
  for (const a of additions) {
    if (!existing.includes(a)) existing.push(a)
  }
  return existing
}

function removeClass(
  className: unknown,
  ...removals: string[]
): Array<string | number> {
  let existing: Array<string | number>
  if (Array.isArray(className)) {
    existing = [...className] as Array<string | number>
  } else if (typeof className === "string" && className.trim() !== "") {
    existing = className.split(/\s+/).filter(Boolean)
  } else {
    existing = []
  }
  return existing.filter((c) => !removals.includes(String(c)))
}

function makeDiv(cls: string, children: ElementContent[]): Element {
  return {
    type: "element",
    tagName: "div",
    properties: { className: [cls] },
    children,
  }
}

function makeTextDiv(cls: string, text: string): Element {
  return makeDiv(cls, [{ type: "text", value: text }])
}

function promoteListToCards(list: Element, ordered: boolean): void {
  const classes = ["shiny-chat-suggestion-list"]
  if (ordered) classes.push("shiny-chat-suggestion-list--ordered")
  list.properties.className = appendClass(list.properties.className, ...classes)
  list.properties.role = "list"

  let itemIndex = 0

  for (const child of list.children) {
    if (child.type !== "element" || child.tagName !== "li") continue

    const liKids = child.children as ElementContent[]
    const suggestionEl = significantChildren(liKids).find(
      isSuggestionElement,
    ) as Element

    const bodyText = getTextContent(suggestionEl.children as RootContent[])

    const rawTitle = suggestionEl.properties.title
    const titleStr =
      typeof rawTitle === "string" && rawTitle.trim() !== ""
        ? rawTitle.trim()
        : null

    let titleEl: Element | null = null

    if (ordered) {
      const prefix = `${itemIndex + 1}.`
      const titleText = titleStr ? `${prefix} ${titleStr}` : prefix
      titleEl = makeTextDiv("shiny-chat-suggestion-list-item-title", titleText)
    } else if (titleStr) {
      titleEl = makeTextDiv("shiny-chat-suggestion-list-item-title", titleStr)
    }

    const bodyEl = makeDiv(
      "shiny-chat-suggestion-list-item-body",
      suggestionEl.children as ElementContent[],
    )

    suggestionEl.children = titleEl ? [titleEl, bodyEl] : [bodyEl]

    suggestionEl.properties.className = appendClass(
      suggestionEl.properties.className,
      "shiny-chat-suggestion-list-item",
    )

    const existingDs = suggestionEl.properties.dataSuggestion
    if (!(typeof existingDs === "string" && existingDs !== "")) {
      suggestionEl.properties.dataSuggestion = bodyText
    }

    // aria-label: always set (overwriting any label from rehypeAccessibleSuggestions)
    // so the announcement reflects the full visible card content.
    if (ordered) {
      const n = itemIndex + 1
      suggestionEl.properties.ariaLabel = titleStr
        ? `Use chat suggestion #${n}: ${titleStr} — ${bodyText}`
        : `Use chat suggestion #${n}: ${bodyText}`
    } else {
      suggestionEl.properties.ariaLabel = titleStr
        ? `Use chat suggestion: ${titleStr} — ${bodyText}`
        : `Use chat suggestion: ${bodyText}`
    }

    // CSS custom property for staggered animation; avoids the @for Sass loop.
    const existingStyle = suggestionEl.properties.style
    const styleDecl = `--_card-index:${itemIndex}`
    suggestionEl.properties.style =
      typeof existingStyle === "string" && existingStyle !== ""
        ? `${styleDecl};${existingStyle}`
        : styleDecl

    delete suggestionEl.properties.title

    // role="listitem" on the <li> so the list/listitem pairing is announced
    // correctly even when CSS resets the default list role.
    ;(child as Element).properties.role = "listitem"

    itemIndex++
  }
}

/**
 * Determine whether a trailing (last top-level) list should be treated as a
 * pending suggestion list while it is still being streamed.
 *
 * This function is ONLY called for the last top-level block, which is by
 * definition still mid-stream. The final <li> is therefore treated as
 * in-progress and is excluded from disqualification checks — while a
 * suggestion span is being emitted, the parser may surface it as a plain-text
 * node (e.g. `<span class="suggestion"`) before the tag closes. Skipping the
 * last <li> prevents a jarring flip from pending cards back to a plain bullet
 * list and then back again as the markup completes.
 *
 * On stream end, `finalizePendingSuggestionLists` re-runs the strict
 * `isQualifyingList` check. If the final state doesn't actually qualify the
 * pending marker is cleanly removed — no permanent false promotion.
 *
 * A list is pending when ALL of the following hold:
 *   1. Every direct <li> child EXCEPT the last one is either:
 *      (a) empty / whitespace-only, OR
 *      (b) contains EXACTLY one significant child (whitespace text nodes are
 *          ignored) AND that child is a suggestion element.
 *   2. At least one non-last <li> satisfies (b), OR the list has only a
 *      single <li> (which is itself the in-progress last item).
 *
 * Any non-last <li> that has a suggestion element alongside other significant
 * content (trailing text, a second element, etc.) immediately disqualifies
 * the list, as does any non-last <li> whose sole significant child is plain
 * text.
 *
 * We only inspect direct <li> children so a qualifying nested list does not
 * promote its outer list. Once a new block-level element follows the list in
 * the tree the list is no longer trailing and is re-evaluated through the
 * strict isQualifyingList path instead.
 */
function isPendingSuggestionList(node: Element): boolean {
  const kids = node.children as ElementContent[]
  const elements = kids.filter((c) => c.type === "element") as Element[]
  if (elements.length === 0) return false

  // A single <li> is itself the in-progress last item — allow pending so the
  // very first suggestion card doesn't flash as an unstyled bullet while
  // the span is still being streamed.
  if (elements.length === 1) {
    return elements[0]!.tagName === "li"
  }

  // Evaluate all <li> elements except the last; the last is in-progress.
  const nonLast = elements.slice(0, -1)
  let sawSuggestion = false

  for (const el of nonLast) {
    if (el.tagName !== "li") return false

    const liKids = el.children as ElementContent[]
    const sig = significantChildren(liKids)

    if (sig.length === 0) {
      // (a) empty / whitespace-only — allowed
      continue
    }

    if (sig.length === 1 && isSuggestionElement(sig[0]!)) {
      // (b) exactly one significant child that is a suggestion element
      sawSuggestion = true
      continue
    }

    // Any other combination disqualifies the list
    return false
  }

  // Also verify the last element is an <li> (not some other tag)
  if (elements[elements.length - 1]!.tagName !== "li") return false

  return sawSuggestion
}

function markListPending(list: Element, ordered: boolean): void {
  const classes = ["shiny-chat-suggestion-list"]
  if (ordered) classes.push("shiny-chat-suggestion-list--ordered")
  list.properties.className = appendClass(list.properties.className, ...classes)
  list.properties[SUGGESTION_PENDING_ATTR] = ""
}

function lastElementChild(children: RootContent[]): Element | null {
  for (let i = children.length - 1; i >= 0; i--) {
    const child = children[i]
    if (child && child.type === "element") return child
  }
  return null
}

export const rehypeSuggestionCards: Plugin<[], Root> = () => (tree) => {
  const lastEl = lastElementChild(tree.children)

  for (const child of tree.children) {
    if (child.type !== "element") continue
    const el = child as Element
    if (el.tagName !== "ul" && el.tagName !== "ol") continue

    // Trailing list: stay in (or enter) pending while it is the last
    // top-level block. Never promote here — even a fully-qualifying
    // trailing list may still be mid-stream (the model may be about
    // to add another item). Promotion happens only when a new block
    // follows (below) or when streaming ends and
    // finalizePendingSuggestionLists runs.
    if (el === lastEl) {
      if (isPendingSuggestionList(el)) {
        markListPending(el, el.tagName === "ol")
      }
      continue
    }

    // A new block follows this list → it is finalized. Promote if it
    // qualifies; otherwise leave it as a regular list.
    if (isQualifyingList(el)) {
      promoteListToCards(el, el.tagName === "ol")
    }
  }
}

/**
 * Shallow-copy the pending list's spine down to the suggestion element level
 * so that `promoteListToCards` can mutate the copy without touching the cached
 * original HAST. The copies share reference to all unmodified subtrees.
 *
 * Spine: list → li[] → suggestion element inside each li.
 */
function cloneListForPromotion(original: Element): Element {
  const el: Element = {
    ...original,
    properties: { ...original.properties },
    // Clone the children array so we can replace individual li entries.
    children: original.children.map((child) => {
      if (child.type !== "element" || child.tagName !== "li") return child
      const li = child as Element
      // Clone the li and its children array so promoteListToCards can splice.
      const liCopy: Element = {
        ...li,
        properties: { ...li.properties },
        children: li.children.map((liChild) => {
          if (!isSuggestionElement(liChild)) return liChild
          // Clone the suggestion element itself — promoteListToCards mutates
          // its .properties and .children.
          const suggEl = liChild as Element
          return {
            ...suggEl,
            properties: { ...suggEl.properties },
            // children are re-wrapped by promoteListToCards, so a shallow copy
            // of the array is sufficient (the child nodes themselves are not mutated).
            children: [...suggEl.children],
          } as Element
        }),
      }
      return liCopy
    }),
  }
  return el
}

/**
 * Finalize pending suggestion lists at end-of-stream.
 *
 * Called from `hastToReact` when `streaming` is false. Returns a NEW Root
 * with only the pending list's spine shallow-copied (sibling subtrees are
 * shared by reference), mirroring the path-copy strategy used by
 * `withStreamingDot`. If no pending list is found the original tree is
 * returned unchanged (identity return — no allocation).
 *
 * The cached HAST passed in is never mutated.
 */
export function finalizePendingSuggestionLists(tree: Root): Root {
  // Find indices of pending lists so we can decide whether any work is needed.
  const pendingIndices: number[] = []
  for (let i = 0; i < tree.children.length; i++) {
    const child = tree.children[i]
    if (!child || child.type !== "element") continue
    const el = child as Element
    if (el.tagName !== "ul" && el.tagName !== "ol") continue
    if (el.properties && SUGGESTION_PENDING_ATTR in el.properties)
      pendingIndices.push(i)
  }

  if (pendingIndices.length === 0) return tree

  // Shallow-copy the root children array; non-pending children are shared.
  const newChildren = [...tree.children] as RootContent[]

  for (const idx of pendingIndices) {
    const original = newChildren[idx] as Element

    // Deep-copy the list spine so promoteListToCards can mutate safely
    // without touching the cached original HAST.
    const el = cloneListForPromotion(original)
    newChildren[idx] = el as RootContent

    delete el.properties[SUGGESTION_PENDING_ATTR]

    if (isQualifyingList(el)) {
      promoteListToCards(el, el.tagName === "ol")
    } else {
      el.properties.className = removeClass(
        el.properties.className,
        "shiny-chat-suggestion-list",
        "shiny-chat-suggestion-list--ordered",
      )
      if (
        Array.isArray(el.properties.className) &&
        el.properties.className.length === 0
      ) {
        delete el.properties.className
      }
    }
  }

  return { ...tree, children: newChildren }
}

// Re-export shared helpers that other modules (e.g. streamingDot) consume via
// this module to avoid having to update every importer.
export { hasSuggestionClass, getTextContent, isSuggestionElement }
