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
  let activeActivity: Element | null = null
  const citationsByActivity = new Map<Element, CitationSource[]>()

  visit(tree, "element", (node: Element) => {
    if (node.tagName === "shiny-web-activity") {
      activeActivity = hasSearchResults(node) ? null : node
      return
    }
    if (!activeActivity || node.tagName !== "shiny-aside") return
    const source = citationSource(node)
    if (!source) return
    const citations = citationsByActivity.get(activeActivity) ?? []
    citations.push(source)
    citationsByActivity.set(activeActivity, citations)
  })

  for (const [activity, citations] of citationsByActivity) {
    activity.properties = {
      ...activity.properties,
      citedSources: JSON.stringify(mergeSources(citations)),
    }
  }
}

/**
 * Attach answer citations to the preceding web-activity burst without a
 * provider result list. These are cited sources, not a synthetic result set.
 */
export const rehypeAttachCitedSources: Plugin<[], Root> = () => transform
