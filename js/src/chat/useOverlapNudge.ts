import { useEffect, useRef, type RefObject } from "react"

export interface OverlapNudgeOptions {
  // When false the hook is inert (no measuring, no observers).
  enabled?: boolean
  // Selector for the boundary the element is anchored within and measured
  // against. Obstacles are hit-tested elements outside this boundary, so the
  // chat's own content and layout parents are ignored, leaving genuine siblings
  // (e.g. a sidebar toggle).
  boundarySelector: string
  // CSS custom property (set on the element) that shifts it inward, in px.
  shiftProperty: string
  // Which of the element's edges leads toward potential obstacles. A function
  // is re-read on every measure, so it can track a dynamic placement attribute.
  side: "left" | "right" | ((boundary: HTMLElement) => "left" | "right")
  // Clearance gap left between the element and an obstacle once nudged.
  gap?: number
  // Cap the shift to this fraction of the boundary's width, so the element never
  // travels too far into the content.
  maxShiftFraction?: number
  // Return true to skip measuring and preserve the last shift — e.g. while the
  // element sits under an overlay so its position is moot and probing would
  // record a false "no overlap".
  shouldSkip?: (boundary: HTMLElement) => boolean
  // Opt-in: watch the boundary for mutations that reposition obstacles or change
  // skip state (e.g. an overlay added/removed within it) and re-measure.
  watchMutations?: MutationObserverInit
}

// Keep an element anchored to a corner of a boundary clear of unrelated UI that
// overlaps its home position (e.g. a bslib sidebar reveal button). When the
// element's leading edge overlaps an element outside the boundary, nudge it
// inward via `shiftProperty` until it clears, capped by `maxShiftFraction`.
export function useOverlapNudge<T extends HTMLElement>(
  elementRef: RefObject<T | null>,
  options: OverlapNudgeOptions,
): void {
  const optionsRef = useRef(options)
  optionsRef.current = options

  const { enabled = true, boundarySelector } = options

  useEffect(() => {
    if (!enabled) return
    const element = elementRef.current
    if (!element) return
    const boundary = element.closest<HTMLElement>(boundarySelector)
    if (!boundary) return

    const update = (): void => {
      const {
        shiftProperty,
        side,
        gap = 8,
        maxShiftFraction = 1 / 3,
        shouldSkip,
      } = optionsRef.current

      if (shouldSkip?.(boundary)) return

      const placeRight =
        (typeof side === "function" ? side(boundary) : side) === "right"

      // Measure from the home position each time so the shift never compounds.
      element.style.setProperty(shiftProperty, "0px")
      const rect = element.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return

      // Probe the element's leading (outer) edge at three heights. An obstacle is
      // any hit-tested element that is neither inside the boundary nor an ancestor
      // of it (which filters out the boundary's own content and its backdrops/
      // layout parents, leaving genuine siblings).
      const edgeX = placeRight ? rect.right - 1 : rect.left + 1
      const ys = [rect.top + 2, rect.top + rect.height / 2, rect.bottom - 2]

      let obstacleEdge: number | null = null
      for (const y of ys) {
        const obstacle = document
          .elementsFromPoint(edgeX, y)
          .find((el) => !boundary.contains(el) && !el.contains(boundary))
        if (!obstacle) continue
        const obRect = obstacle.getBoundingClientRect()
        const edge = placeRight ? obRect.left : obRect.right
        obstacleEdge =
          obstacleEdge === null
            ? edge
            : placeRight
              ? Math.min(obstacleEdge, edge)
              : Math.max(obstacleEdge, edge)
      }

      if (obstacleEdge === null) return

      const shift = placeRight
        ? rect.right - obstacleEdge + gap
        : obstacleEdge - rect.left + gap
      if (shift <= 0) return

      const maxShift = boundary.clientWidth * maxShiftFraction
      element.style.setProperty(shiftProperty, `${Math.min(shift, maxShift)}px`)
    }

    update()

    const ro = new ResizeObserver(update)
    ro.observe(boundary)
    window.addEventListener("resize", update)

    // A sidebar collapse/expand shifts the boundary without resizing it; the
    // layout toggles a class and animates, so re-measure on both.
    const layout = boundary.closest(".bslib-sidebar-layout")
    layout?.addEventListener("transitionend", update)
    const layoutMo = layout ? new MutationObserver(update) : null
    layoutMo?.observe(layout!, { attributes: true, attributeFilter: ["class"] })

    const { watchMutations } = optionsRef.current
    const watchMo = watchMutations ? new MutationObserver(update) : null
    watchMo?.observe(boundary, watchMutations!)

    return () => {
      ro.disconnect()
      window.removeEventListener("resize", update)
      layout?.removeEventListener("transitionend", update)
      layoutMo?.disconnect()
      watchMo?.disconnect()
    }
  }, [enabled, boundarySelector, elementRef])
}
