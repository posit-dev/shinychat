import { useEffect, useRef } from "react"

// Renders raw HTML via a ref, opting out of React's DOM management.
// This prevents React from resetting innerHTML on re-render, which
// would destroy content injected by external systems (e.g. Shiny
// output bindings for widget charts and input elements).
export function RawHTML({
  html,
  className,
}: {
  html: string
  className?: string
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = html
    }
  }, [html])
  return <div ref={ref} className={className} />
}
