import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type RefCallback,
} from "react"

export interface UseAutoScrollOptions {
  /** Is content actively streaming? */
  streaming: boolean
  /** Value that changes when content updates (e.g., messages array or content string).
   *  Used as a useEffect dependency to trigger scroll checks during streaming. */
  contentDependency: unknown
  /** Pixel tolerance for "at bottom" detection. Default: 10 */
  bottomTolerance?: number
  /** When true, scroll to bottom on any content change while stickToBottom
   *  is engaged, not just during streaming. Default: false. */
  scrollOnContentChange?: boolean
}

export interface UseAutoScrollReturn {
  /** Callback ref — attach to the scrollable container element. */
  containerRef: RefCallback<HTMLElement>
  /** Whether auto-scroll is engaged. False when the user has scrolled away. */
  stickToBottom: boolean
  /** Manually scroll to bottom and re-engage auto-scroll. */
  scrollToBottom: () => void
  /** Re-engage stickToBottom without performing an immediate scroll.
   *  Useful when a content change is about to happen and the post-render
   *  effect should handle scrolling with the correct scrollHeight. */
  engageStickToBottom: () => void
}

/**
 * Auto-scrolls a container to the bottom during streaming, disengaging when the
 * user scrolls up and re-engaging when they scroll back to the bottom.
 *
 * Uses direction-based detection (comparing scrollTop to its previous value)
 * rather than flag-based detection. The scroll listener is attached once via a
 * callback ref and is never torn down/re-registered during content changes.
 */
export function useAutoScroll({
  streaming,
  contentDependency,
  bottomTolerance = 10,
  scrollOnContentChange = false,
}: UseAutoScrollOptions): UseAutoScrollReturn {
  const containerElRef = useRef<HTMLElement | null>(null)
  const [stickToBottom, setStickToBottom] = useState(true)
  const prevScrollTopRef = useRef<number>(0)

  // Check scroll position and update stickToBottom.
  // Direction-based: scrollTop decreased → user scrolled up → disengage.
  // At bottom (within tolerance) → re-engage.
  const checkScrollPosition = useCallback(() => {
    const el = containerElRef.current
    if (!el) return

    const { scrollTop, scrollHeight, clientHeight } = el
    const isAtBottom =
      scrollTop + clientHeight >= scrollHeight - bottomTolerance
    const isScrollingUp = scrollTop < prevScrollTopRef.current
    prevScrollTopRef.current = scrollTop

    if (isScrollingUp) {
      setStickToBottom(false)
    } else if (isAtBottom) {
      setStickToBottom(true)
    }
  }, [bottomTolerance])

  // Store in a ref so the callback ref closure always calls the latest version
  const checkScrollPositionRef = useRef(checkScrollPosition)
  checkScrollPositionRef.current = checkScrollPosition

  // Stable handler that delegates to the ref — this is what gets registered as
  // the scroll listener, so it never goes stale even though the callback ref
  // closure is captured once.
  const stableScrollHandler = useRef((): void => {
    checkScrollPositionRef.current()
  })

  // Callback ref: attaches the scroll listener when the element mounts and
  // removes it when the element unmounts. Fires exactly once per mount/unmount
  // cycle — no teardown on content changes.
  const containerRef = useCallback<RefCallback<HTMLElement>>((node) => {
    if (containerElRef.current) {
      containerElRef.current.removeEventListener(
        "scroll",
        stableScrollHandler.current,
      )
    }

    containerElRef.current = node

    if (node) {
      prevScrollTopRef.current = node.scrollTop
      node.addEventListener("scroll", stableScrollHandler.current, {
        passive: true,
      })
    }
  }, [])

  // Auto-scroll during streaming (or on any content change if scrollOnContentChange
  // is set) when stickToBottom is true.
  // contentDependency is included so that each new chunk triggers the scroll.
  useEffect(() => {
    const shouldScroll = streaming || scrollOnContentChange
    if (shouldScroll && stickToBottom && containerElRef.current) {
      containerElRef.current.scrollTo({
        top: containerElRef.current.scrollHeight,
        // Use "instant" during streaming: rapid content updates would cancel
        // each "smooth" animation before it reaches its target, causing the
        // scroll position to fall behind.
        behavior: streaming ? "instant" : "smooth",
      })
    }
  }, [streaming, stickToBottom, contentDependency, scrollOnContentChange])

  // Manually re-engage and scroll to bottom
  const scrollToBottom = useCallback(() => {
    setStickToBottom(true)
    containerElRef.current?.scrollTo({
      top: containerElRef.current.scrollHeight,
      behavior: "smooth",
    })
  }, [])

  const engageStickToBottom = useCallback(() => {
    setStickToBottom(true)
  }, [])

  return { containerRef, stickToBottom, scrollToBottom, engageStickToBottom }
}

/**
 * Walks up the DOM from `startEl` to find the nearest scrollable ancestor.
 * Stops if it hits an element with tag `stopAtTag` (exclusive).
 * Returns `null` if no scrollable ancestor is found.
 */
export function findScrollableParent(
  startEl: HTMLElement,
  stopAtTag?: string,
): HTMLElement | null {
  let el: HTMLElement | null = startEl.parentElement
  const stopTag = stopAtTag?.toLowerCase()

  while (el) {
    if (stopTag && el.tagName.toLowerCase() === stopTag) break

    const style = getComputedStyle(el)
    const allowsVerticalScroll =
      style.overflowY !== "hidden" && style.overflowY !== "clip"
    const hasScrollableContent = el.scrollHeight > el.clientHeight

    if (
      (allowsVerticalScroll && hasScrollableContent) ||
      style.overflowY === "auto" ||
      style.overflowY === "scroll" ||
      style.overflowY === "overlay"
    ) {
      return el
    }

    el = el.parentElement
  }

  return null
}
