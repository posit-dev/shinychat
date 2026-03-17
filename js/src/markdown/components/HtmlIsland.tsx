// SECURITY: assistant-only — do not add to user markdown components.
import { toHtml } from "hast-util-to-html"
import { useEffect, useMemo, useRef, useState } from "react"
import type { Element } from "hast"

interface HtmlIslandProps {
  node?: Element
  children?: React.ReactNode
}

export function HtmlIsland({ node }: HtmlIslandProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [isFillCarrier, setIsFillCarrier] = useState(false)
  const html = useMemo(() => (node ? toHtml(node.children) : ""), [node])

  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = html
      const parent = ref.current.parentElement
      if (parent?.classList.contains("html-fill-container")) {
        setIsFillCarrier(true)
      }
    }
  }, [html])

  return (
    <div
      ref={ref}
      className={
        isFillCarrier ? "html-fill-item html-fill-container" : undefined
      }
      style={{ display: "contents" }}
    />
  )
}
