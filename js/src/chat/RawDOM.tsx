import { useEffect, useRef } from "react"

// Adopts pre-bound DOM nodes from a source element into the React tree.
// Unlike RawHTML (which sets innerHTML from a string and binds from scratch),
// this preserves existing Shiny bindings by moving the original nodes.
export function RawDOM({
  source,
  className,
}: {
  source: Element
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    while (source.firstChild) {
      el.appendChild(source.firstChild)
    }
    return () => {
      while (el.firstChild) {
        source.appendChild(el.firstChild)
      }
    }
  }, [source])

  return <div ref={ref} className={className} />
}
