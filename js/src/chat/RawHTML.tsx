import { useEffect, useRef } from "react"

// Uses a ref to opt out of React's DOM management, preventing React from
// resetting innerHTML and destroying content injected by Shiny bindings.
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
