import { useEffect, useRef } from "react"
import type { ShinyLifecycle } from "../transport/types"
import type { ContentType } from "../transport/types"

/**
 * Manages Shiny DOM binding/unbinding for a markdown content container.
 *
 * Key design decisions:
 * 1. During streaming, cleanup does NOT call unbindAll between chunks —
 *    it only cancels the pending setTimeout. This fixes a bug where widgets
 *    were being unbound and rebound on every ~50ms chunk arrival.
 * 2. A separate mount-only effect handles unbindAll on true unmount,
 *    covering the mid-stream component removal case.
 * 3. bindAll during streaming is throttled to at most once per 200ms.
 */
export function useShinyBinding(
  containerRef: React.RefObject<HTMLElement | null>,
  shiny: ShinyLifecycle,
  options: { content: string; streaming: boolean; contentType: ContentType },
): void {
  const { content, streaming, contentType } = options
  const isText = contentType === "text"
  const lastBindTimeRef = useRef(0)

  // Track the latest isText value in a ref so the mount-only unmount effect
  // can read it without needing to be in the dependency array.
  const isTextRef = useRef(isText)
  isTextRef.current = isText

  useEffect(() => {
    if (isText) return
    const el = containerRef.current
    if (!el) return

    if (streaming) {
      // Throttle: bind at most once per 200ms during streaming
      const now = Date.now()
      const elapsed = now - lastBindTimeRef.current
      const delay = Math.max(0, 200 - elapsed)

      const timeout = setTimeout(() => {
        shiny.bindAll(el)
        lastBindTimeRef.current = Date.now()
      }, delay)

      // DO NOT unbindAll here — the next chunk's bindAll covers it.
      // Only clean up the pending timeout.
      return () => {
        clearTimeout(timeout)
      }
    }

    // Not streaming: bind immediately, unbind on cleanup
    shiny.bindAll(el)
    return () => {
      shiny.unbindAll(el)
    }
  }, [content, streaming, isText, shiny, containerRef])

  // On true unmount (component removed from tree), always unbind.
  // This catches the case where the component unmounts mid-stream
  // (the streaming effect above doesn't unbind between chunks).
  useEffect(() => {
    return () => {
      if (isTextRef.current) return
      // eslint-disable-next-line react-hooks/exhaustive-deps
      const el = containerRef.current
      if (el) shiny.unbindAll(el)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
}
