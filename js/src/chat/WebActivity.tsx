import { memo, useState } from "react"
import type { ComponentType } from "react"
import type { Element, ElementContent } from "hast"
import { externalLinkAttributes } from "../markdown/plugins/rehypeExternalLinks"
import { isSafeUrl } from "../markdown/urlSanitize"
import {
  normalizeSources,
  type WebActivityItem,
  type WebActivitySearchItem,
  type WebActivitySource,
} from "./web-activity-model"
import { ChevronIcon } from "./ChevronIcon"
import { useAsideFavicon } from "./context"
import { domainFromUrl } from "./domain"

interface WebActivityProps {
  items: WebActivityItem[]
}

function prop(el: Element, name: string): string | undefined {
  const v = el.properties?.[name]
  return typeof v === "string" ? v : undefined
}

function parseSources(json?: string): WebActivitySource[] {
  if (!json) return []
  try {
    return normalizeSources(JSON.parse(json))
  } catch {
    return []
  }
}

/**
 * Parse a <shiny-web-activity> HAST subtree (the markup path) into
 * structured items. Search↔results pairing uses a pending-search queue: a
 * results element attaches its sources to the earliest search still lacking
 * them, or becomes a query-less search item when none is pending. The
 * reducer's applyWebBlock re-expresses this same pairing for web_* blocks.
 *
 * The wrapper's `citedSources` property (attached by
 * rehypeAttachCitedSources when a burst has no provider result list) is the
 * markup-path form of the answer-citation fallback; the structured path
 * carries it as `cited_sources` on the web_search block instead.
 */
function parseItems(node?: Element): WebActivityItem[] {
  if (!node) return []
  const citedSources = parseSources(prop(node, "citedSources"))
  const kids = (node.children ?? []).filter(
    (c: ElementContent): c is Element => c.type === "element",
  )
  const items: WebActivityItem[] = []
  const pendingSearches: WebActivitySearchItem[] = []
  for (const el of kids) {
    if (el.tagName === "shiny-web-search") {
      const search: WebActivitySearchItem = {
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

function domainOf(s: WebActivitySource): string {
  return s.domain || domainFromUrl(s.url)
}

// Fires one external request per unique domain (only when the panel is
// expanded). Air-gapped deployments will see the onError glyph fallback.
function faviconUrl(domain: string): string {
  return `https://icons.duckduckgo.com/ip3/${encodeURIComponent(domain)}.ico`
}

/**
 * Renders one web-activity burst (searches + fetches) as a collapsible
 * timeline. Takes structured items — built by the reducer from web_* wire
 * blocks, or by WebActivityBridge from a <shiny-web-activity> HAST subtree
 * on the markup path.
 */
export const WebActivity = memo(function WebActivity({
  items,
}: WebActivityProps) {
  const [expanded, setExpanded] = useState(false)
  const deriveFavicon = useAsideFavicon()
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
                          {sources.map((s) => {
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

/**
 * Component-map bridge for the markup path: a <shiny-web-activity> element
 * (grouped by rehypeGroupWebActivity out of server-authored markup, e.g. R
 * until its Phase 3 port) parses into the structured items WebActivity
 * renders.
 */
export const WebActivityBridge = (({ node }: { node?: Element }) => (
  <WebActivity items={parseItems(node)} />
)) as ComponentType<unknown>
