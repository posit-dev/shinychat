import { memo, useState } from "react"
import type { Element, ElementContent } from "hast"
import { externalLinkAttributes } from "../markdown/plugins/rehypeExternalLinks"
import { isSafeUrl } from "../markdown/urlSanitize"
import { ChevronIcon } from "./ChevronIcon"
import { useAsideFavicon } from "./context"
import { domainFromUrl } from "./domain"

interface Source {
  url: string
  title?: string
  domain?: string
}

interface SearchItem {
  kind: "search"
  query: string
  sources: Source[] | null
  citedSources: Source[]
}

interface FetchItem {
  kind: "fetch"
  url: string
  status?: string
}

type Item = SearchItem | FetchItem

interface WebActivityProps {
  node?: Element
}

function prop(el: Element, name: string): string | undefined {
  const v = el.properties?.[name]
  return typeof v === "string" ? v : undefined
}

function parseSources(json?: string): Source[] {
  if (!json) return []
  try {
    const arr: unknown = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    const seen = new Set<string>()
    return arr.filter((s): s is Source => {
      if (!s || typeof (s as Source).url !== "string") return false
      const url = (s as Source).url
      if (seen.has(url)) return false
      seen.add(url)
      return true
    })
  } catch {
    return []
  }
}

function parseItems(node?: Element): Item[] {
  if (!node) return []
  const citedSources = parseSources(prop(node, "citedSources"))
  const kids = (node.children ?? []).filter(
    (c: ElementContent): c is Element => c.type === "element",
  )
  const items: Item[] = []
  const pendingSearches: SearchItem[] = []
  for (const el of kids) {
    if (el.tagName === "shiny-web-search") {
      const search: SearchItem = {
        kind: "search",
        query: prop(el, "query") ?? "",
        sources: null,
        citedSources: [],
      }
      items.push(search)
      pendingSearches.push(search)
    } else if (el.tagName === "shiny-web-search-results") {
      const sources = parseSources(prop(el, "sources"))
      const search = pendingSearches.shift()
      if (search) {
        search.sources = sources
      } else {
        items.push({
          kind: "search",
          query: "",
          sources,
          citedSources: [],
        })
      }
    } else if (el.tagName === "shiny-web-fetch") {
      const url = prop(el, "url")
      if (url) items.push({ kind: "fetch", url, status: prop(el, "status") })
    }
  }
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index]!
    if (item.kind === "search" && item.sources === null) {
      item.citedSources = citedSources
      break
    }
  }
  return items
}

function domainOf(s: Source): string {
  return s.domain || domainFromUrl(s.url)
}

// Fires one external request per unique domain (only when the panel is
// expanded). Air-gapped deployments will see the onError glyph fallback.
function faviconUrl(domain: string): string {
  return `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`
}

export const WebActivity = memo(function WebActivity({
  node,
}: WebActivityProps) {
  const [expanded, setExpanded] = useState(false)
  const deriveFavicon = useAsideFavicon()
  const items = parseItems(node)
  if (items.length === 0) return null

  const headerText = items.some((it) => it.kind === "search")
    ? "Searched the web"
    : "Read the web"

  return (
    <div className="shiny-web-activity">
      <button
        className="shiny-web-activity__header"
        aria-expanded={expanded}
        onClick={() => setExpanded((p) => !p)}
      >
        <ChevronIcon
          className="shiny-web-activity__chevron"
          expanded={expanded}
        />
        {headerText}
      </button>
      {expanded && (
        <div className="shiny-web-activity__timeline">
          {items.map((item, idx) =>
            item.kind === "search" ? (
              <div
                key={`search-${idx}-${item.query}`}
                className="shiny-web-activity__node shiny-web-activity__search"
              >
                {/*
                 * Provider result lists describe search results. Citation rows
                 * are an answer-side fallback when that list is unavailable.
                 */}
                {(() => {
                  const sources = item.sources ?? item.citedSources
                  const isCitedFallback =
                    item.sources === null && item.citedSources.length > 0
                  return (
                    <>
                      <div className="shiny-web-activity__qrow">
                        <span className="shiny-web-activity__query">
                          {item.query}
                        </span>
                        {item.sources !== null && item.sources.length > 0 && (
                          <span className="shiny-web-activity__count">
                            {item.sources.length} result
                            {item.sources.length !== 1 ? "s" : ""}
                          </span>
                        )}
                        {isCitedFallback && (
                          <span className="shiny-web-activity__count">
                            Cited sources
                          </span>
                        )}
                      </div>
                      {sources.length > 0 && (
                        <div className="shiny-web-activity__results">
                          {sources.map((s, j) => {
                            const domain = domainOf(s)
                            const safe = isSafeUrl(s.url)
                            const Row = safe ? "a" : "span"
                            return (
                              <Row
                                key={s.url}
                                className="shiny-web-activity__result"
                                {...(safe
                                  ? {
                                      href: s.url,
                                      ...externalLinkAttributes,
                                    }
                                  : {})}
                              >
                                {deriveFavicon && (
                                  <img
                                    className="shiny-web-activity__fav"
                                    src={faviconUrl(domain)}
                                    alt=""
                                    loading="lazy"
                                    onError={(e) => {
                                      e.currentTarget.style.visibility =
                                        "hidden"
                                    }}
                                  />
                                )}
                                <span className="shiny-web-activity__title">
                                  {s.title || domain}
                                </span>
                                <span className="shiny-web-activity__domain">
                                  {domain}
                                </span>
                              </Row>
                            )
                          })}
                        </div>
                      )}
                    </>
                  )
                })()}
              </div>
            ) : (
              <div
                key={`fetch-${idx}-${item.url}`}
                className="shiny-web-activity__node shiny-web-activity__fetch"
              >
                <span className="shiny-web-activity__fetch-label">Read</span>
                {item.status !== "error" && isSafeUrl(item.url) ? (
                  <a href={item.url} {...externalLinkAttributes}>
                    {item.url}
                  </a>
                ) : (
                  <span>{item.url}</span>
                )}
                <span
                  className={`shiny-web-activity__status shiny-web-activity__status--${
                    item.status === "error" ? "error" : "ok"
                  }`}
                  aria-label={item.status === "error" ? "failed" : "succeeded"}
                >
                  {item.status === "error" ? "✗" : "✓"}
                </span>
              </div>
            ),
          )}
        </div>
      )}
    </div>
  )
})
