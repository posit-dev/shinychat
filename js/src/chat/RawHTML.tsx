import { useContext, useEffect, useRef, useState } from "react"
import { ShinyLifecycleContext } from "./context"

// Uses a ref to opt out of React's DOM management, preventing React from
// resetting innerHTML and destroying content injected by Shiny bindings.
//
// When ShinyLifecycleContext is available, automatically calls bindAll/unbindAll
// scoped to this element — each RawHTML instance manages its own Shiny bindings.
export function RawHTML({
  html,
  className,
  displayContents = true,
  fillable = true,
}: {
  html: string
  className?: string
  displayContents?: boolean
  /**
   * Whether to join the fill layout when the parent is a fill container, so a
   * Shiny output payload (a plot, a value box) can absorb the available height
   * instead of collapsing. Pass `false` for card chrome — a footer is sized by
   * its content, and promoting it makes it split the free space with the body.
   */
  fillable?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [isFillCarrier, setIsFillCarrier] = useState(false)
  const shiny = useContext(ShinyLifecycleContext)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    el.innerHTML = html

    const parent = el.parentElement
    setIsFillCarrier(
      fillable && !!parent?.classList.contains("html-fill-container"),
    )

    if (shiny && html) {
      shiny.bindAll(el)
    }

    return () => {
      if (shiny && el) {
        shiny.unbindAll(el)
      }
    }
  }, [html, shiny, fillable])

  return (
    <div
      ref={ref}
      className={
        isFillCarrier
          ? `html-fill-item html-fill-container${className ? ` ${className}` : ""}`
          : className
      }
      style={displayContents ? { display: "contents" } : undefined}
    />
  )
}
