import { memo, useEffect, useState } from "react"
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  FloatingPortal,
  FloatingFocusManager,
  useHover,
  useFocus,
  useClick,
  useDismiss,
  useRole,
  useInteractions,
} from "@floating-ui/react"
import type { Element } from "hast"
import { toHtml } from "hast-util-to-html"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ASIDE_PENDING_ATTR } from "../markdown/plugins/markTrailingAsides"
import { externalLinkAttributes } from "../markdown/plugins/rehypeExternalLinks"
import { useAsideFavicon } from "./context"

export interface AsideEntry {
  label?: string
  url?: string
  icon?: string
  body?: string
  index?: number
}

interface AsideGroupProps {
  node?: Element
}

function prop(el: Element, name: string): string | undefined {
  const v = el.properties?.[name]
  return typeof v === "string" ? v : undefined
}

function numProp(el: Element, name: string): number | undefined {
  const v = el.properties?.[name]
  return typeof v === "number" ? v : undefined
}

export function parseAsideEntries(node?: Element): AsideEntry[] {
  if (!node) return []
  return (node.children ?? [])
    .filter(
      (c): c is Element => c.type === "element" && c.tagName === "shiny-aside",
    )
    .map((el) => ({
      label: prop(el, "label"),
      url: prop(el, "url"),
      icon: prop(el, "icon"),
      body: el.children.length > 0 ? toHtml(el.children) : undefined,
      index: numProp(el, "index"),
    }))
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

// Gap between the pill and the popover (see .shiny-aside-popover's `top`
// offset) is a dead zone the pointer must cross when moving from one to the
// other. useHover's `delay.close` keeps the popover alive long enough to
// reach it, and is canceled automatically if the pointer lands back on the
// pill or the popover before it elapses.
const CLOSE_GRACE_PERIOD_MS = 150

export const AsideGroup = memo(function AsideGroup({ node }: AsideGroupProps) {
  const entries = parseAsideEntries(node)
  const deriveFavicon = useAsideFavicon()
  const faceIndex = entries.findIndex((e) => e.label)
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)

  // strategy: "fixed" + the middleware below let the popover escape the
  // message list's `overflow: auto` (needed for scrolling, so it can't just
  // be set to visible) and reposition itself (flip above the pill, shift
  // within the viewport) when there isn't room where it'd normally go.
  const { refs, floatingStyles, context } = useFloating({
    open,
    onOpenChange: setOpen,
    strategy: "fixed",
    placement: "bottom-start",
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })

  // Composed rather than hand-rolled: useHover already tracks pointer entry
  // on both the pill and the popover (canceling the close delay if the
  // pointer lands on either), and useClick's open event marks the popover as
  // "click-opened" so useHover no longer auto-closes it on mouse-leave —
  // i.e. clicking pins it, clicking again un-pins and closes it.
  const hover = useHover(context, { delay: { close: CLOSE_GRACE_PERIOD_MS } })
  const focus = useFocus(context)
  const click = useClick(context)
  const dismiss = useDismiss(context, { outsidePressEvent: "mousedown" })
  const role = useRole(context)

  const { getReferenceProps, getFloatingProps } = useInteractions([
    hover,
    focus,
    click,
    dismiss,
    role,
  ])

  // Reset paging to the face entry whenever the popover opens, regardless of
  // which interaction (hover, focus, click) opened it.
  useEffect(() => {
    if (open) setIndex(faceIndex === -1 ? 0 : faceIndex)
  }, [open, faceIndex])

  // Withheld while its surrounding block is still streaming (see
  // rehypeMarkTrailingAsides) so the pill doesn't flash in mid-sentence.
  if (node?.properties?.[ASIDE_PENDING_ATTR] != null) return null
  if (entries.length === 0) return null
  const overflow = entries.length - 1
  const allSameLabel =
    faceIndex !== -1 &&
    entries.every((e) => e.label === entries[faceIndex]!.label)
  const showOverflow = overflow > 0 && !allSameLabel

  const current = entries[index]!
  const pillLabel =
    faceIndex === -1
      ? `Aside ${entries[0]!.index}`
      : showOverflow
        ? `${entries[faceIndex]!.label} (+${overflow} more)`
        : entries[faceIndex]!.label

  return (
    <span className="shiny-aside-group">
      <button
        ref={refs.setReference}
        type="button"
        className={
          faceIndex === -1
            ? "shiny-aside-pill shiny-aside-pill--count"
            : "shiny-aside-pill"
        }
        aria-label={pillLabel}
        {...getReferenceProps()}
      >
        {faceIndex !== -1 && (
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
        {faceIndex === -1 && entries[0]!.index}
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
              style={floatingStyles}
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
                  <span className="shiny-aside-popover__count">
                    {index + 1} / {entries.length}
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
                      {current.label}
                    </a>
                  ) : (
                    <div className="shiny-aside-popover__label">
                      <EntryIcon
                        entry={current}
                        deriveFavicon={deriveFavicon}
                      />
                      {current.label}
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
