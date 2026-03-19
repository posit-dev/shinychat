import {
  useCallback,
  useLayoutEffect,
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
 * user scrolls away from the bottom and re-engaging when they scroll back.
 *
 * Uses position-based detection: on every user-initiated scroll event, checks
 * whether the element is near the bottom and sets stickToBottom accordingly.
 * A programmatic-scroll guard (isProgrammaticScrollRef) suppresses scroll event
 * processing during our own scrollTo calls, preventing false disengagement when
 * content height fluctuates during streaming.
 *
 * The scroll listener is attached once via a callback ref and is never
 * torn down/re-registered during content changes.
 */
export function useAutoScroll({
  streaming,
  contentDependency,
  bottomTolerance = 10,
  scrollOnContentChange = false,
}: UseAutoScrollOptions): UseAutoScrollReturn {
  const containerElRef = useRef<HTMLElement | null>(null)
  const [stickToBottom, setStickToBottom] = useState(true)
  const isProgrammaticScrollRef = useRef(false)

  const checkScrollPosition = useCallback(() => {
    const el = containerElRef.current
    if (!el || isProgrammaticScrollRef.current) return

    const { scrollTop, scrollHeight, clientHeight } = el
    const isAtBottom =
      scrollTop + clientHeight >= scrollHeight - bottomTolerance
    setStickToBottom(isAtBottom)
  }, [bottomTolerance])

  const checkScrollPositionRef = useRef(checkScrollPosition)
  checkScrollPositionRef.current = checkScrollPosition

  // Stable identity: captured once by the callback ref, delegates to the latest logic
  const stableScrollHandler = useRef((): void => {
    checkScrollPositionRef.current()
  })

  const containerRef = useCallback<RefCallback<HTMLElement>>((node) => {
    if (containerElRef.current) {
      containerElRef.current.removeEventListener(
        "scroll",
        stableScrollHandler.current,
      )
    }

    containerElRef.current = node

    if (node) {
      node.addEventListener("scroll", stableScrollHandler.current, {
        passive: true,
      })
    }
  }, [])

  // contentDependency is in the deps so each new chunk triggers a scroll
  useLayoutEffect(() => {
    const shouldScroll = streaming || scrollOnContentChange
    if (shouldScroll && stickToBottom && containerElRef.current) {
      isProgrammaticScrollRef.current = true
      containerElRef.current.scrollTo({
        top: containerElRef.current.scrollHeight,
        // Use "instant" during streaming: rapid content updates would cancel
        // each "smooth" animation before it reaches its target, causing the
        // scroll position to fall behind.
        behavior: streaming ? "instant" : "smooth",
      })
      requestAnimationFrame(() => {
        isProgrammaticScrollRef.current = false
      })
    }
  }, [streaming, stickToBottom, contentDependency, scrollOnContentChange])

  const scrollToBottom = useCallback(() => {
    setStickToBottom(true)
    if (containerElRef.current) {
      isProgrammaticScrollRef.current = true
      containerElRef.current.scrollTo({
        top: containerElRef.current.scrollHeight,
        behavior: "smooth",
      })
      requestAnimationFrame(() => {
        isProgrammaticScrollRef.current = false
      })
    }
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

    if (allowsVerticalScroll && hasScrollableContent) {
      return el
    }

    el = el.parentElement
  }

  return null
}
