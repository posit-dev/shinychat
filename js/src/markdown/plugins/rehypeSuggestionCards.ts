import type { Root, Element, ElementContent, RootContent } from "hast"
import type { Plugin } from "unified"

function hasSuggestionClass(className: unknown): boolean {
  if (typeof className === "string") {
    return className.split(/\s+/).includes("suggestion")
  }
  if (Array.isArray(className)) return className.includes("suggestion")
  return false
}

function getTextContent(children: RootContent[] | undefined): string {
  if (!children) return ""

  return children
    .map((child) => {
      if (child.type === "text") return child.value
      if (child.type === "element") return getTextContent(child.children)
      return ""
    })
    .join("")
    .trim()
}

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

function isSuggestionElement(node: ElementContent): node is Element {
  if (node.type !== "element") return false
  const props = node.properties
  if (!props) return false
  return hasSuggestionClass(props.className) || "dataSuggestion" in props
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

    delete suggestionEl.properties.title

    itemIndex++
  }
}

function liHasDirectSuggestion(li: Element): boolean {
  for (const child of li.children) {
    if (isSuggestionElement(child)) return true
  }
  return false
}

// Lenient: a trailing list is "pending" as soon as any <li> has a
// direct suggestion child. We do not constrain what the other <li>s
// contain — they may hold partial raw HTML being streamed (e.g. an
// unclosed `<span class="suggestion"` that the parser surfaces as
// text, or stray text from a half-typed item). Pending sticks for the
// entire stream of the list because the caller only invokes us while
// the list is the last top-level child; once a new block lands after
// it, the list is re-evaluated through the strict qualifying path
// instead. We check direct <li> children only so a qualifying list
// nested inside another <li> does not promote the outer list.
function isPendingSuggestionList(node: Element): boolean {
  const kids = node.children as ElementContent[]
  const elements = kids.filter((c) => c.type === "element") as Element[]
  if (elements.length === 0) return false

  let sawSuggestion = false
  for (const el of elements) {
    if (el.tagName !== "li") return false
    if (liHasDirectSuggestion(el)) sawSuggestion = true
  }
  return sawSuggestion
}

function markListPending(list: Element, ordered: boolean): void {
  const classes = ["shiny-chat-suggestion-list"]
  if (ordered) classes.push("shiny-chat-suggestion-list--ordered")
  list.properties.className = appendClass(list.properties.className, ...classes)
  list.properties.dataPending = ""
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
 * Finalize pending suggestion lists at end-of-stream.
 *
 * Called from `hastToReact` when `streaming` is false. For each
 * top-level list marked `data-pending`: if it now qualifies, promote
 * to cards; otherwise strip the pending markers and let it render as
 * a native list.
 */
export function finalizePendingSuggestionLists(tree: Root): void {
  for (const child of tree.children) {
    if (child.type !== "element") continue
    const el = child as Element
    if (el.tagName !== "ul" && el.tagName !== "ol") continue
    const props = el.properties
    if (!props || !("dataPending" in props)) continue

    delete props.dataPending

    if (isQualifyingList(el)) {
      promoteListToCards(el, el.tagName === "ol")
    } else {
      props.className = removeClass(
        props.className,
        "shiny-chat-suggestion-list",
        "shiny-chat-suggestion-list--ordered",
      )
      if (Array.isArray(props.className) && props.className.length === 0) {
        delete props.className
      }
    }
  }
}
