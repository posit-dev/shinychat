import { memo, useEffect, useId, useState } from "react"
import { FloatingPortal, FloatingFocusManager } from "@floating-ui/react"
import type { Element as HastElement } from "hast"
import { toHtml } from "hast-util-to-html"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ASIDE_PENDING_ATTR } from "../markdown/plugins/markTrailingAsides"
import { externalLinkAttributes } from "../markdown/plugins/rehypeExternalLinks"
import { useAsideFavicon } from "./context"
import { useCitationRegister } from "./citationCollector"
import { citationEntriesFromAsides, type CitationEntry } from "./citations"
import { domainFromUrl } from "./domain"
import { portalTheme } from "./portalTheme"
import { useDismissiblePopover } from "./useDismissiblePopover"

export interface CitationMetadata {
  title?: string
  cited_quote?: string
}

export interface AsideEntry {
  label?: string
  url?: string
  icon?: string
  body?: string
  index?: number
  citation?: CitationMetadata
  groundingId?: string
}

interface AsideGroupProps {
  node?: HastElement
}

interface AsideGroupViewProps {
  entries: AsideEntry[]
  pending?: boolean
}

function prop(el: HastElement, name: string): string | undefined {
  const v = el.properties?.[name]
  return typeof v === "string" ? v : undefined
}

function numProp(el: HastElement, name: string): number | undefined {
  const v = el.properties?.[name]
  return typeof v === "number" ? v : undefined
}

function textContent(node: HastElement): string {
  return node.children
    .map((child) => {
      if (child.type === "text") return child.value
      if (child.type === "element") return textContent(child)
      return ""
    })
    .join("")
}

export function parseAsideEntries(node?: HastElement): AsideEntry[] {
  if (!node) return []
  return (node.children ?? [])
    .filter(
      (c): c is HastElement =>
        c.type === "element" && c.tagName === "shiny-aside",
    )
    .map((el) => {
      const url = prop(el, "url")
      const label = prop(el, "label")
      const text = textContent(el).trim()
      const citation =
        el.properties?.dataCitation == null
          ? undefined
          : {
              title: text === "" || text === url ? undefined : text,
              cited_quote: prop(el, "cited-quote"),
            }
      return {
        label: label ?? (citation && url ? domainFromUrl(url) : undefined),
        url,
        icon: prop(el, "icon"),
        body: el.children.length > 0 ? toHtml(el.children) : undefined,
        index: numProp(el, "index"),
        citation,
        groundingId: prop(el, "dataGroundingId"),
      }
    })
}

export function faviconUrl(url: string): string | undefined {
  try {
    return `https://icons.duckduckgo.com/ip3/${encodeURIComponent(new URL(url).hostname)}.ico`
  } catch {
    return undefined
  }
}

function EntryIcon({
  entry,
  deriveFavicon,
}: {
  entry: AsideEntry
  deriveFavicon: boolean
}) {
  const src =
    entry.icon ||
    (deriveFavicon && entry.url ? faviconUrl(entry.url) : undefined)
  // Track which src failed (rather than a bare boolean) so that a later entry
  // with a different src — e.g. when paging the popover — gets a fresh attempt
  // instead of inheriting the previous entry's failure.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  // Unmount on error rather than hiding with display:none: a hidden-but-present
  // <img> still satisfies the pill's `:has(img)` padding rule, so an aside
  // whose favicon fails would keep the reduced start padding despite showing
  // no icon.
  if (!src || failedSrc === src) return null
  return <img src={src} alt="" onError={() => setFailedSrc(src)} />
}

function NavArrowIcon({ direction }: { direction: "prev" | "next" }) {
  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      style={direction === "prev" ? { transform: "scaleX(-1)" } : undefined}
    >
      <path
        d="M4.5 2.5L8 6L4.5 9.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export const AsideGroup = memo(function AsideGroup({ node }: AsideGroupProps) {
  const entries = parseAsideEntries(node)
  const pending = node?.properties?.[ASIDE_PENDING_ATTR] != null
  return <AsideGroupView entries={entries} pending={pending} />
})

export const AsideGroupView = memo(function AsideGroupView({
  entries,
  pending = false,
}: AsideGroupViewProps) {
  const deriveFavicon = useAsideFavicon()
  const faceIndex = entries.findIndex((e) => e.label)
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)
  const registry = useCitationRegister()
  const instanceId = useId()
  const citationSignature = !pending
    ? JSON.stringify(citationEntriesFromAsides(entries))
    : ""
  const activeGroundingId = entries[index]?.groundingId

  const { refs, floatingStyles, context, getReferenceProps, getFloatingProps } =
    useDismissiblePopover(open, setOpen)

  useEffect(() => {
    if (!registry || citationSignature === "") return
    const citations = JSON.parse(citationSignature) as CitationEntry[]
    if (citations.length === 0) return
    registry.register(instanceId, citations)
    return () => registry.unregister(instanceId)
  }, [registry, instanceId, citationSignature])

  // Reset paging to the face entry whenever the popover opens, regardless of
  // which interaction (hover, focus, click) opened it.
  useEffect(() => {
    if (open) setIndex(faceIndex === -1 ? 0 : faceIndex)
  }, [open, faceIndex])

  useEffect(() => {
    if (!open || !activeGroundingId) return
    const reference = refs.domReference.current
    if (!(reference instanceof HTMLElement)) return
    const container = reference.closest("p, li")
    if (!container) return

    const grounded = [
      ...container.querySelectorAll<HTMLElement>("[data-aside-grounding]"),
    ].filter((element) =>
      element.dataset.asideGrounding?.split(" ").includes(activeGroundingId),
    )
    for (const element of grounded) element.dataset.active = ""
    return () => {
      for (const element of grounded) delete element.dataset.active
    }
  }, [open, activeGroundingId, refs.domReference])

  // Withheld while its surrounding block is still streaming (see
  // rehypeMarkTrailingAsides) so the pill doesn't flash in mid-sentence.
  if (pending) return null
  if (entries.length === 0) return null
  const overflow = entries.length - 1
  const allSameLabel =
    faceIndex !== -1 &&
    entries.every((e) => e.label === entries[faceIndex]!.label)
  const showOverflow = overflow > 0 && !allSameLabel
  const countEntry = entries[0]
  const indexedEntries = entries.filter(
    (entry): entry is AsideEntry & { index: number } =>
      entry.index !== undefined,
  )
  const countMarker =
    indexedEntries.length === entries.length || faceIndex === -1
  const numberMarker =
    indexedEntries.length === entries.length &&
    entries.some((entry) => entry.label !== undefined)
  const countText = indexedEntries.map((entry) => entry.index).join(", ")

  const current = entries[index]!
  const portal = portalTheme(refs.domReference.current)
  const pillLabel = numberMarker
    ? entries.length === 1
      ? `Aside ${countText}: ${countEntry?.label}`
      : `Asides ${countText}: ${entries
          .map((entry) => entry.label ?? "Untitled source")
          .join("; ")}`
    : countMarker
      ? `Aside ${countEntry?.index}`
      : showOverflow
        ? `${entries[faceIndex]!.label} (+${overflow} more)`
        : entries[faceIndex]!.label
  const pillClass = numberMarker
    ? "shiny-aside-pill shiny-aside-pill--count shiny-aside-pill--number"
    : countMarker
      ? "shiny-aside-pill shiny-aside-pill--count"
      : "shiny-aside-pill"

  return (
    <span className="shiny-aside-group">
      <button
        ref={refs.setReference}
        type="button"
        className={pillClass}
        data-shinychat-aside-display={numberMarker ? "compact" : undefined}
        aria-label={pillLabel}
        {...getReferenceProps()}
      >
        {countMarker ? (
          <span className="shiny-aside-pill__count">
            {numberMarker ? `[${countText}]` : countEntry?.index}
          </span>
        ) : (
          <>
            <EntryIcon
              entry={entries[faceIndex]!}
              deriveFavicon={deriveFavicon}
            />
            <span className="shiny-aside-pill__label">
              {entries[faceIndex]!.label}
            </span>
            {showOverflow && (
              <span className="shiny-aside-pill__overflow">+{overflow}</span>
            )}
          </>
        )}
      </button>
      {open && (
        <FloatingPortal>
          <FloatingFocusManager
            context={context}
            modal={false}
            initialFocus={-1}
            returnFocus
          >
            <div
              ref={refs.setFloating}
              className="shiny-aside-popover"
              style={{ ...portal.style, ...floatingStyles }}
              data-bs-theme={portal.theme}
              aria-label={pillLabel}
              {...getFloatingProps()}
            >
              {entries.length > 1 && (
                <div className="shiny-aside-popover__nav">
                  <div className="shiny-aside-popover__nav-arrows">
                    <button
                      type="button"
                      aria-label="Previous source"
                      onClick={() =>
                        setIndex(
                          (i) => (i - 1 + entries.length) % entries.length,
                        )
                      }
                    >
                      <NavArrowIcon direction="prev" />
                    </button>
                    <button
                      type="button"
                      aria-label="Next source"
                      onClick={() => setIndex((i) => (i + 1) % entries.length)}
                    >
                      <NavArrowIcon direction="next" />
                    </button>
                  </div>
                  <span
                    className="shiny-aside-popover__count"
                    aria-hidden="true"
                  >
                    {index + 1} / {entries.length}
                  </span>
                  <span
                    className="visually-hidden"
                    role="status"
                    aria-live="polite"
                    aria-atomic="true"
                  >
                    Source {index + 1} of {entries.length}:{" "}
                    {current.label ?? "Untitled source"}
                  </span>
                </div>
              )}
              {current.label && (
                <>
                  {current.url ? (
                    <a
                      className="shiny-aside-popover__label"
                      href={current.url}
                      {...externalLinkAttributes}
                    >
                      <EntryIcon
                        entry={current}
                        deriveFavicon={deriveFavicon}
                      />
                      <span className="shiny-aside-popover__label-text">
                        {current.label}
                      </span>
                    </a>
                  ) : (
                    <div className="shiny-aside-popover__label">
                      <EntryIcon
                        entry={current}
                        deriveFavicon={deriveFavicon}
                      />
                      <span className="shiny-aside-popover__label-text">
                        {current.label}
                      </span>
                    </div>
                  )}
                </>
              )}
              {current.body && (
                <div className="shiny-aside-popover__body">
                  <MarkdownContent
                    content={current.body}
                    contentType="html"
                    streaming={false}
                  />
                </div>
              )}
            </div>
          </FloatingFocusManager>
        </FloatingPortal>
      )}
    </span>
  )
})
