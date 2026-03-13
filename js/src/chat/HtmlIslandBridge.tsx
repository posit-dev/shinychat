// SECURITY: assistant-only — do not add to userComponents
import { toHtml } from "hast-util-to-html"
import { useEffect, useMemo, useRef } from "react"
import type { Element } from "hast"

interface HtmlIslandBridgeProps {
  node?: Element
  children?: React.ReactNode
}

export function HtmlIslandBridge({ node }: HtmlIslandBridgeProps) {
  const ref = useRef<HTMLDivElement>(null)
  const html = useMemo(() => (node ? toHtml(node.children) : ""), [node])

  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = html
    }
  }, [html])

  return <div ref={ref} />
}
