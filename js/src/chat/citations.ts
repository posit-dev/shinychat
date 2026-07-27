import type { Element, ElementContent } from "hast"

export interface CitationEntry {
  url: string
  domain?: string
  title?: string
}

export function isCitationAside(node: ElementContent): node is Element {
  return (
    node.type === "element" &&
    node.tagName === "shiny-aside" &&
    node.properties != null &&
    "dataCitation" in node.properties
  )
}

function textContent(node: ElementContent): string {
  if (node.type === "text") return node.value
  if (node.type === "element")
    return (node.children ?? []).map(textContent).join("")
  return ""
}

function strProp(el: Element, name: string): string | undefined {
  const v = el.properties?.[name]
  return typeof v === "string" && v !== "" ? v : undefined
}

/**
 * Extract citation entries from a <shiny-aside-group>'s children. Only asides
 * carrying the data-citation marker are considered; hand-authored <shiny-aside>s
 * are ignored so they never appear in the message's Sources summary.
 */
export function citationEntriesFromGroup(node: Element): CitationEntry[] {
  return (node.children ?? [])
    .filter(isCitationAside)
    .map((el) => {
      const url = strProp(el, "url") ?? ""
      const text = textContent(el).trim()
      // Python emits <a>title or url</a>, so text === url means "no real title".
      const title = text === "" || text === url ? undefined : text
      return { url, domain: strProp(el, "label"), title }
    })
    .filter((e) => e.url !== "")
}

/**
 * Collapse citation entries to one per URL, in first-seen order, keeping the
 * first non-empty title encountered for each URL.
 */
export function mergeCitations(entries: CitationEntry[]): CitationEntry[] {
  const byUrl = new Map<string, CitationEntry>()
  for (const e of entries) {
    const existing = byUrl.get(e.url)
    if (!existing) byUrl.set(e.url, { ...e })
    else if (!existing.title && e.title) existing.title = e.title
  }
  return [...byUrl.values()]
}
