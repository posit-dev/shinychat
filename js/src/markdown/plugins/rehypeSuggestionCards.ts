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
): string | Array<string | number> {
  if (Array.isArray(className)) {
    return [...className, ...additions] as Array<string | number>
  }
  if (typeof className === "string" && className.trim() !== "") {
    return [className, ...additions]
  }
  return [...additions]
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

export const rehypeSuggestionCards: Plugin<[], Root> = () => (tree) => {
  for (const child of tree.children) {
    if (child.type !== "element") continue
    const el = child as Element
    if (el.tagName !== "ul" && el.tagName !== "ol") continue
    if (!isQualifyingList(el)) continue
    promoteListToCards(el, el.tagName === "ol")
  }
}
