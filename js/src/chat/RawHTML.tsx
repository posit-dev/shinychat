import { useContext, useEffect, useRef, useState } from "react"
import { ShinyLifecycleContext } from "../chat/context"

// Uses a ref to opt out of React's DOM management, preventing React from
// resetting innerHTML and destroying content injected by Shiny bindings.
//
// When ShinyLifecycleContext is available, automatically calls bindAll/unbindAll
// scoped to this element — each RawHTML instance manages its own Shiny bindings.
export function RawHTML({
  html,
  className,
  displayContents = false,
}: {
  html: string
  className?: string
  displayContents?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [isFillCarrier, setIsFillCarrier] = useState(false)
  const shiny = useContext(ShinyLifecycleContext)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    el.innerHTML = html

    if (displayContents) {
      const parent = el.parentElement
      if (parent?.classList.contains("html-fill-container")) {
        setIsFillCarrier(true)
      }
    }

    if (shiny && html) {
      shiny.bindAll(el)
    }

    return () => {
      if (shiny && el) {
        shiny.unbindAll(el)
      }
    }
  }, [html, displayContents, shiny])

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
