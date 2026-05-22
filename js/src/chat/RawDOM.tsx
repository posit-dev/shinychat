import { useContext, useEffect, useRef } from "react"
import { ShinyLifecycleContext } from "./context"

// Adopts DOM nodes from a source element into the React tree, managing
// Shiny binding lifecycle around each move. Unbinds before moving nodes
// in, rebinds after; reverses on cleanup so nodes survive React unmount.
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
