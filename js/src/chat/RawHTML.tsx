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
  as: Tag = "div",
  bind = true,
  displayContents = true,
  fillable = true,
}: {
  html: string
  className?: string
  /**
   * Use "span" when the island sits in a phrasing-content context (a <span>
   * or <button>), where a <div> would be invalid nesting.
   */
  as?: "div" | "span"
  /**
   * Pass `false` when the same server HTML is mounted elsewhere (e.g. an
   * expanded tool row also mounts the full card) so only one copy owns the
   * Shiny bindings; binding both would register duplicate Shiny ids.
   */
  bind?: boolean
  displayContents?: boolean
  /**
   * Whether to join the fill layout when the parent is a fill container, so a
   * Shiny output payload (a plot, a value box) can absorb the available height
   * instead of collapsing. Pass `false` for card chrome — a footer is sized by
   * its content, and promoting it makes it split the free space with the body.
   */
  fillable?: boolean
}) {
  const ref = useRef<HTMLElement | null>(null)
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

    if (shiny && html && bind) {
      shiny.bindAll(el)
    }

    return () => {
      if (shiny && bind) {
        shiny.unbindAll(el)
      }
    }
    // `Tag` is a dep because switching it remounts the element.
  }, [html, shiny, fillable, bind, Tag])

  return (
    <Tag
      // Callback ref: Tag's union type gives the ref prop a union of
      // HTMLDivElement/HTMLSpanElement types; HTMLElement is the common base.
      ref={(el: HTMLElement | null) => {
        ref.current = el
      }}
      className={
        isFillCarrier
          ? `html-fill-item html-fill-container${className ? ` ${className}` : ""}`
          : className
      }
      style={displayContents ? { display: "contents" } : undefined}
    />
  )
}
