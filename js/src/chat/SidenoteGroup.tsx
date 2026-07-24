import { memo, useEffect, useRef, useState } from "react"
import type { KeyboardEvent, FocusEvent } from "react"
import {
  useFloating,
  autoUpdate,
  offset,
  flip,
  shift,
  FloatingPortal,
} from "@floating-ui/react"
import type { Element } from "hast"
import { toHtml } from "hast-util-to-html"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { SIDENOTE_PENDING_ATTR } from "../markdown/plugins/markTrailingSidenotes"

export interface SidenoteEntry {
  label?: string
  url?: string
  icon?: string
  body?: string
  index?: number
}

interface SidenoteGroupProps {
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

export function parseSidenoteEntries(node?: Element): SidenoteEntry[] {
  if (!node) return []
  return (node.children ?? [])
    .filter(
      (c): c is Element =>
        c.type === "element" && c.tagName === "shiny-sidenote",
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

function EntryIcon({ entry }: { entry: SidenoteEntry }) {
  const src = entry.icon || (entry.url ? faviconUrl(entry.url) : undefined)
  // Track which src failed (rather than a bare boolean) so that a later entry
  // with a different src — e.g. when paging the popover — gets a fresh attempt
  // instead of inheriting the previous entry's failure.
  const [failedSrc, setFailedSrc] = useState<string | null>(null)
  // Unmount on error rather than hiding with display:none: a hidden-but-present
  // <img> still satisfies the pill's `:has(img)` padding rule, so a sidenote
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

// Gap between the pill and the popover (see .shiny-sidenote-popover's `top`
// offset) is a dead zone the pointer must cross when moving from one to the
// other. Closing on a delay — canceled if the pointer lands back inside
// before it elapses — keeps the popover alive long enough to reach.
const CLOSE_GRACE_PERIOD_MS = 150

// The popover renders through a portal, so it's no longer a DOM descendant
// of the group span — "did this click/blur target land inside our own
// widget" checks must also consider the floating element.
function isInsideWidget(
  node: Node | null,
  containerEl: HTMLElement | null,
  floatingEl: HTMLElement | null,
) {
  return !!node && (containerEl?.contains(node) || floatingEl?.contains(node))
}

export const SidenoteGroup = memo(function SidenoteGroup({
  node,
}: SidenoteGroupProps) {
  const entries = parseSidenoteEntries(node)
  const faceIndex = entries.findIndex((e) => e.label)
  const [open, setOpen] = useState(false)
  const [pinned, setPinned] = useState(false)
  const [index, setIndex] = useState(0)
  const containerRef = useRef<HTMLSpanElement>(null)
  const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // strategy: "fixed" + the middleware below let the popover escape the
  // message list's `overflow: auto` (needed for scrolling, so it can't just
  // be set to visible) and reposition itself (flip above the pill, shift
  // within the viewport) when there isn't room where it'd normally go.
  const { refs, floatingStyles } = useFloating({
    open,
    strategy: "fixed",
    placement: "bottom-start",
    middleware: [offset(6), flip(), shift({ padding: 8 })],
    whileElementsMounted: autoUpdate,
  })

  function cancelScheduledClose() {
    if (closeTimeoutRef.current !== null) {
      clearTimeout(closeTimeoutRef.current)
      closeTimeoutRef.current = null
    }
  }

  useEffect(() => cancelScheduledClose, [])

  useEffect(() => {
    if (!pinned) return
    function onDocMouseDown(e: MouseEvent) {
      if (
        !isInsideWidget(
          e.target as Node,
          containerRef.current,
          refs.floating.current,
        )
      ) {
        setOpen(false)
        setPinned(false)
      }
    }
    document.addEventListener("mousedown", onDocMouseDown)
    return () => document.removeEventListener("mousedown", onDocMouseDown)
  }, [pinned, refs.floating])

  // Withheld while its surrounding block is still streaming (see
  // rehypeMarkTrailingSidenotes) so the pill doesn't flash in mid-sentence.
  if (node?.properties?.[SIDENOTE_PENDING_ATTR] != null) return null
  if (entries.length === 0) return null
  const overflow = entries.length - 1
  const allSameLabel =
    faceIndex !== -1 &&
    entries.every((e) => e.label === entries[faceIndex]!.label)
  const showOverflow = overflow > 0 && !allSameLabel

  function show() {
    cancelScheduledClose()
    setIndex(faceIndex === -1 ? 0 : faceIndex)
    setOpen(true)
  }
  function hideUnlessPinned() {
    if (pinned) return
    cancelScheduledClose()
    closeTimeoutRef.current = setTimeout(() => {
      closeTimeoutRef.current = null
      setOpen(false)
    }, CLOSE_GRACE_PERIOD_MS)
  }
  function togglePinned() {
    if (pinned) {
      setPinned(false)
      setOpen(false)
    } else {
      setPinned(true)
      show()
    }
  }
  function handleKeyDown(e: KeyboardEvent<HTMLSpanElement>) {
    if (e.key === "Escape") {
      setOpen(false)
      setPinned(false)
      ;(document.activeElement as HTMLElement | null)?.blur()
    }
  }
  function handleBlur(e: FocusEvent<HTMLSpanElement>) {
    if (
      !pinned &&
      !isInsideWidget(
        e.relatedTarget as Node | null,
        containerRef.current,
        refs.floating.current,
      )
    ) {
      setOpen(false)
    }
  }

  const current = entries[index]!
  const pillLabel =
    faceIndex === -1
      ? `Sidenote ${entries[0]!.index}`
      : showOverflow
        ? `${entries[faceIndex]!.label} (+${overflow} more)`
        : entries[faceIndex]!.label

  return (
    <span
      ref={containerRef}
      className="shiny-sidenote-group"
      onMouseEnter={show}
      onMouseLeave={hideUnlessPinned}
      onKeyDown={handleKeyDown}
      onBlur={handleBlur}
    >
      <button
        ref={refs.setReference}
        type="button"
        className={
          faceIndex === -1
            ? "shiny-sidenote-pill shiny-sidenote-pill--count"
            : "shiny-sidenote-pill"
        }
        onClick={togglePinned}
        onFocus={show}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={pillLabel}
      >
        {faceIndex !== -1 && (
          <>
            <EntryIcon entry={entries[faceIndex]!} />
            <span className="shiny-sidenote-pill__label">
              {entries[faceIndex]!.label}
            </span>
            {showOverflow && (
              <span className="shiny-sidenote-pill__overflow">+{overflow}</span>
            )}
          </>
        )}
        {faceIndex === -1 && entries[0]!.index}
      </button>
      {open && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            className="shiny-sidenote-popover"
            role="dialog"
            style={floatingStyles}
          >
            {entries.length > 1 && (
              <div className="shiny-sidenote-popover__nav">
                <div className="shiny-sidenote-popover__nav-arrows">
                  <button
                    type="button"
                    aria-label="Previous source"
                    onClick={() =>
                      setIndex((i) => (i - 1 + entries.length) % entries.length)
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
                <span className="shiny-sidenote-popover__count">
                  {index + 1} / {entries.length}
                </span>
              </div>
            )}
            {current.label && (
              <div className="shiny-sidenote-popover__label">
                <EntryIcon entry={current} />
                {current.label}
              </div>
            )}
            {current.body && (
              <div className="shiny-sidenote-popover__body">
                <MarkdownContent
                  content={current.body}
                  contentType="html"
                  streaming={false}
                />
              </div>
            )}
          </div>
        </FloatingPortal>
      )}
    </span>
  )
})
