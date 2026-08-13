import { visit } from "unist-util-visit"
import type { Element, Root } from "hast"
import type { Plugin } from "unified"

interface CitationSource {
  url: string
  title?: string
}

function prop(el: Element, name: string): string | undefined {
  const value = el.properties?.[name]
  return typeof value === "string" ? value : undefined
}

function textContent(el: Element): string {
  return el.children
    .map((child) => {
      if (child.type === "text") return child.value
      if (child.type === "element") return textContent(child)
      return ""
    })
    .join("")
    .trim()
}

function citationSource(el: Element): CitationSource | null {
  if (el.properties?.dataCitation == null) return null
  const url = prop(el, "url")
  if (!url) return null
  const title = textContent(el)
  return title === "" || title === url ? { url } : { url, title }
}

function hasSearchResults(activity: Element): boolean {
  return activity.children.some(
    (child) =>
      child.type === "element" && child.tagName === "shiny-web-search-results",
  )
}

function mergeSources(sources: CitationSource[]): CitationSource[] {
  const byUrl = new Map<string, CitationSource>()
  for (const source of sources) {
    const existing = byUrl.get(source.url)
    if (!existing) {
      byUrl.set(source.url, source)
    } else if (!existing.title && source.title) {
      existing.title = source.title
    }
  }
  return [...byUrl.values()]
}

function transform(tree: Root): void {
  const activities: Element[] = []
  const citations: CitationSource[] = []

  visit(tree, "element", (node: Element) => {
    if (node.tagName === "shiny-web-activity") activities.push(node)
    if (node.tagName !== "shiny-aside") return
    const source = citationSource(node)
    if (source) citations.push(source)
  })

  if (citations.length === 0) return
  for (let index = activities.length - 1; index >= 0; index -= 1) {
    const activity = activities[index]!
    if (hasSearchResults(activity)) continue
    activity.properties = {
      ...activity.properties,
      citedSources: JSON.stringify(mergeSources(citations)),
    }
    return
  }
}

/**
 * Attach final-answer citations to the last web-activity burst without a
 * provider result list. These are cited sources, not a synthetic result set.
 */
export const rehypeAttachCitedSources: Plugin<[], Root> = () => transform
