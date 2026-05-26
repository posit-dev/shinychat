import { useContext, useEffect, useRef } from "react"
import { ShinyLifecycleContext } from "./context"

// Complement to RawHTML: both use a ref div to opt out of React's DOM
// management and both manage Shiny bindings via ShinyLifecycleContext.
// RawHTML reconstructs DOM from an HTML string; RawDOM adopts existing
// DOM nodes by moving them from a source element. This preserves event
// listeners, widget state, and any other DOM state that a
// serialization round-trip through innerHTML would destroy.
//
// On setup: unbinds the source, moves children into the React-managed
// div, then rebinds in the new location. On cleanup: unbinds, moves
// children back to the source so they survive React unmount and can be
// re-adopted on remount (e.g. when the custom element is moved in the
// DOM, triggering disconnectedCallback → connectedCallback).
//
// Safety: the effect deps [source, shiny] are both referentially stable
// for the lifetime of the component — source is a DOM element stored as
// a private field on the custom element instance, and shiny is a
// window-global singleton provided via context — so the effect runs
// exactly once per mount.
export function RawDOM({
  source,
  className,
}: {
  source: Element
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  const shiny = useContext(ShinyLifecycleContext)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    if (shiny) shiny.unbindAll(source as HTMLElement)
    while (source.firstChild) {
      el.appendChild(source.firstChild)
    }
    if (shiny) shiny.bindAll(el)

    return () => {
      if (shiny) shiny.unbindAll(el)
      while (el.firstChild) {
        source.appendChild(el.firstChild)
      }
    }
  }, [source, shiny])

  return <div ref={ref} className={className} />
}
