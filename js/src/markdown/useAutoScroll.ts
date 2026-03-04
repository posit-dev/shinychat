import { useEffect, useRef, useCallback, type RefObject } from "react"

interface UseAutoScrollOptions {
  autoScroll: boolean
  streaming: boolean
  content: string
  containerTag?: string // stop searching for scrollable parent at this tag
}

/**
 * Custom hook that auto-scrolls the nearest scrollable parent to the bottom
 * when content changes, unless the user has manually scrolled away.
 *
 * Ported from the current MarkdownElement scroll logic.
 */
export function useAutoScroll(
  containerRef: RefObject<HTMLElement | null>,
  options: UseAutoScrollOptions,
): void {
  const { autoScroll, streaming, content, containerTag = "shiny-chat-container" } = options
  const scrollableRef = useRef<HTMLElement | null>(null)
  const isUserScrolledRef = useRef(false)
  const isContentChangingRef = useRef(false)

  const isNearBottom = useCallback((): boolean => {
    const el = scrollableRef.current
    if (!el) return false
    return el.scrollHeight - (el.scrollTop + el.clientHeight) < 50
  }, [])

  const onScroll = useCallback(() => {
    if (!isContentChangingRef.current) {
      isUserScrolledRef.current = !isNearBottom()
    }
  }, [isNearBottom])

  // Find and track scrollable parent
  useEffect(() => {
    if (!autoScroll || !containerRef.current) {
      scrollableRef.current = null
      return
    }

    let el: HTMLElement | null = containerRef.current
    let found: HTMLElement | null = null

    while (el) {
      if (el.scrollHeight > el.clientHeight) {
        found = el
        break
      }
      el = el.parentElement
      if (el?.tagName?.toLowerCase() === containerTag.toLowerCase()) {
        break
      }
    }

    if (found !== scrollableRef.current) {
      scrollableRef.current?.removeEventListener("scroll", onScroll)
      scrollableRef.current = found
      scrollableRef.current?.addEventListener("scroll", onScroll)
    }

    return () => {
      scrollableRef.current?.removeEventListener("scroll", onScroll)
    }
  }, [autoScroll, containerRef, onScroll, containerTag])

  // Scroll to bottom when content changes
  useEffect(() => {
    isContentChangingRef.current = true

    const el = scrollableRef.current
    if (el && !isUserScrolledRef.current) {
      el.scroll({
        top: el.scrollHeight - el.clientHeight,
        behavior: streaming ? "instant" : "smooth",
      })
    }

    isContentChangingRef.current = false
  }, [content, streaming])
}
