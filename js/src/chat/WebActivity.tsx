import { memo, useState } from "react"
import type { Element, ElementContent } from "hast"
import { isSafeUrl } from "../markdown/urlSanitize"

interface Source {
  url: string
  title?: string
  domain?: string
}

interface SearchItem {
  kind: "search"
  query: string
  sources: Source[]
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
  const kids = (node.children ?? []).filter(
    (c: ElementContent): c is Element => c.type === "element",
  )
  const items: Item[] = []
  for (let i = 0; i < kids.length; i++) {
    const el = kids[i]!
    if (el.tagName === "shiny-web-search") {
      let sources: Source[] = []
      const next = kids[i + 1]
      if (next && next.tagName === "shiny-web-search-results") {
        sources = parseSources(prop(next, "sources"))
        i++
      }
      items.push({ kind: "search", query: prop(el, "query") ?? "", sources })
    } else if (el.tagName === "shiny-web-search-results") {
      items.push({
        kind: "search",
        query: "",
        sources: parseSources(prop(el, "sources")),
      })
    } else if (el.tagName === "shiny-web-fetch") {
      const url = prop(el, "url")
      if (url) items.push({ kind: "fetch", url, status: prop(el, "status") })
    }
  }
  return items
}

function domainOf(s: Source): string {
  if (s.domain) return s.domain
  try {
    return new URL(s.url).hostname
  } catch {
    return s.url
  }
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
        <span
          className="shiny-web-activity__chevron"
          data-expanded={expanded || undefined}
          aria-hidden="true"
        >
          ›
        </span>
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
                <div className="shiny-web-activity__qrow">
                  <span className="shiny-web-activity__query">
                    {item.query}
                  </span>
                  <span className="shiny-web-activity__count">
                    {item.sources.length} result
                    {item.sources.length !== 1 ? "s" : ""}
                  </span>
                </div>
                {item.sources.length > 0 && (
                  <div className="shiny-web-activity__results">
                    {item.sources.map((s, j) => {
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
                                target: "_blank",
                                rel: "noopener noreferrer",
                              }
                            : {})}
                        >
                          <img
                            className="shiny-web-activity__fav"
                            src={faviconUrl(domain)}
                            alt=""
                            loading="lazy"
                            onError={(e) => {
                              e.currentTarget.style.visibility = "hidden"
                            }}
                          />
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
              </div>
            ) : (
              <div
                key={`fetch-${idx}-${item.url}`}
                className="shiny-web-activity__node shiny-web-activity__fetch"
              >
                <span className="shiny-web-activity__fetch-label">Read</span>
                {isSafeUrl(item.url) ? (
                  <a href={item.url} target="_blank" rel="noopener noreferrer">
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
