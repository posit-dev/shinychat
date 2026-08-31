import { useContext, useEffect, useRef, useState, type RefObject } from "react"
import { ShinyLifecycleContext } from "./context"

// Uses a ref to opt out of React's DOM management, preventing React from
// resetting innerHTML and destroying content injected by Shiny bindings.
//
// When ShinyLifecycleContext is available, automatically calls bindAll/unbindAll
// scoped to this element — each RawHTML instance manages its own Shiny bindings.

export interface RawHTMLProps {
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
}

export function RawHTML(props: RawHTMLProps) {
  if (props.as === "span") return <RawHTMLSpan {...props} />
  return <RawHTMLDiv {...props} />
}

function useRawHtmlEffect(
  ref: RefObject<HTMLElement | null>,
  html: string,
  bind: boolean,
  fillable: boolean,
) {
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
  }, [html, shiny, fillable, bind, ref])

  return { isFillCarrier }
}

function useRawHtmlClassName(
  isFillCarrier: boolean,
  className: string | undefined,
) {
  return isFillCarrier
    ? `html-fill-item html-fill-container${className ? ` ${className}` : ""}`
    : className
}

function RawHTMLDiv({
  html,
  className,
  bind = true,
  displayContents = true,
  fillable = true,
}: RawHTMLProps) {
  const ref = useRef<HTMLDivElement>(null)
  const { isFillCarrier } = useRawHtmlEffect(ref, html, bind, fillable)

  return (
    <div
      ref={ref}
      className={useRawHtmlClassName(isFillCarrier, className)}
      style={displayContents ? { display: "contents" } : undefined}
    />
  )
}

function RawHTMLSpan({
  html,
  className,
  bind = true,
  displayContents = true,
  fillable = true,
}: RawHTMLProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const { isFillCarrier } = useRawHtmlEffect(ref, html, bind, fillable)

  return (
    <span
      ref={ref}
      className={useRawHtmlClassName(isFillCarrier, className)}
      style={displayContents ? { display: "contents" } : undefined}
    />
  )
}
