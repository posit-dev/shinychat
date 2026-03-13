// SECURITY: assistant-only — do not add to user markdown components.
import { toHtml } from "hast-util-to-html"
import { toJsxRuntime } from "hast-util-to-jsx-runtime"
import { Fragment } from "react"
import { useEffect, useMemo, useRef, type ReactElement } from "react"
import type { Element, ElementContent } from "hast"
import { useComponentMap } from "../componentMapContext"
import { jsx, jsxs } from "../markdownToReact"

interface HtmlIslandProps {
  node?: Element
  children?: React.ReactNode
}

type HtmlSegment = { kind: "html"; html: string }
type ReactSegment = { kind: "react"; node: Element; key: string }
type Segment = HtmlSegment | ReactSegment

function needsReact(child: ElementContent): child is Element {
  return (
    child.type === "element" && child.properties?.["dataShinychatReact"] != null
  )
}

function segmentChildren(children: ElementContent[]): Segment[] {
  const segments: Segment[] = []
  let htmlAccum: ElementContent[] = []

  for (const child of children) {
    if (needsReact(child)) {
      if (htmlAccum.length > 0) {
        segments.push({ kind: "html", html: toHtml(htmlAccum) })
        htmlAccum = []
      }
      const requestId =
        typeof child.properties?.["requestId"] === "string"
          ? child.properties["requestId"]
          : null
      const key = requestId ?? `react-${segments.length}`
      segments.push({ kind: "react", node: child, key })
    } else {
      htmlAccum.push(child)
    }
  }

  if (htmlAccum.length > 0) {
    segments.push({ kind: "html", html: toHtml(htmlAccum) })
  }

  return segments
}

interface RawHtmlSegmentProps {
  html: string
}

function RawHtmlSegment({ html }: RawHtmlSegmentProps) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (ref.current) {
      ref.current.innerHTML = html
    }
  }, [html])

  return <div ref={ref} />
}

interface ReactSegmentProps {
  node: Element
  components: Record<string, React.ComponentType<unknown>>
}

function ReactSegmentComponent({ node, components }: ReactSegmentProps) {
  const element = toJsxRuntime(node, {
    Fragment,
    jsx,
    jsxs,
    components: components as Record<string, React.ComponentType>,
    passKeys: true,
    passNode: true,
    ignoreInvalidStyle: true,
  }) as ReactElement
  return element
}

export function HtmlIsland({ node }: HtmlIslandProps) {
  const componentMap = useComponentMap()
  const segments = useMemo(
    () => (node ? segmentChildren(node.children) : []),
    [node],
  )

  if (segments.length === 0) return null

  return (
    <>
      {segments.map((seg, idx) => {
        if (seg.kind === "html") {
          return <RawHtmlSegment key={idx} html={seg.html} />
        } else {
          return (
            <ReactSegmentComponent
              key={seg.key}
              node={seg.node}
              components={componentMap}
            />
          )
        }
      })}
    </>
  )
}
