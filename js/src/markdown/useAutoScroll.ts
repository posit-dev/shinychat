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
  /** Re-engage stickToBottom if the container is at the bottom *right now*.
   *  Call this immediately before applying a content change, while the DOM still
   *  holds the pre-growth scrollHeight — see the note on scroll-event timing in
   *  the hook's docstring. Only ever engages, never disengages. */
  repinIfAtBottom: () => void
}

/**
 * Auto-scrolls a container to the bottom during streaming, disengaging when the
 * user scrolls up and re-engaging when they scroll back to the bottom.
 *
 * The scroll listener alone cannot be trusted to keep stickToBottom current: it
 * reads geometry when the event is *delivered*, and browsers dispatch scroll
 * events asynchronously (Firefox, from a paint tick that can lag under load). If
 * a content chunk grows scrollHeight in that gap, the user's position no longer
 * reads as "at bottom" while also not reading as "scrolling up", so neither
 * branch fires and auto-scroll disengages permanently (posit-dev/py-shiny#2378).
 * Callers therefore use `repinIfAtBottom()` to settle the question from live
 * geometry at the moment a chunk is applied, when the answer is unambiguous.
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
      prevScrollTopRef.current = node.scrollTop
      node.addEventListener("scroll", stableScrollHandler.current, {
        passive: true,
      })
    }
  }, [])

  // contentDependency is in the deps so each new chunk triggers a scroll
  useEffect(() => {
    const shouldScroll = streaming || scrollOnContentChange
    if (shouldScroll && stickToBottom && containerElRef.current) {
      containerElRef.current.scrollTo({
        top: containerElRef.current.scrollHeight,
        behavior: "smooth",
      })
    }
  }, [streaming, stickToBottom, contentDependency, scrollOnContentChange])

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

  const repinIfAtBottom = useCallback(() => {
    const el = containerElRef.current
    if (!el) return

    const { scrollTop, scrollHeight, clientHeight } = el
    if (scrollTop + clientHeight >= scrollHeight - bottomTolerance) {
      setStickToBottom(true)
    }
    // Deliberately no `else`: chunks routinely arrive while a smooth scroll from
    // the previous chunk is still animating, so "not at the bottom" here does not
    // mean the user scrolled away. Disengaging stays the scroll handler's job.
  }, [bottomTolerance])

  return {
    containerRef,
    stickToBottom,
    scrollToBottom,
    engageStickToBottom,
    repinIfAtBottom,
  }
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
