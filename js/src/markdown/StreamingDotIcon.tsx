import type { ReactElement } from "react"

/**
 * Standalone streaming dot for places with no markdown tree to append it to
 * (e.g. a stream that has produced no content yet). Mirrors the HAST node
 * built by `createDotNode` in streamingDot.ts so both share styling.
 */
export function StreamingDot(): ReactElement {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 12 12"
      xmlns="http://www.w3.org/2000/svg"
      className="markdown-stream-dot"
      style={{ marginLeft: ".25em", marginTop: "-.25em" }}
      aria-hidden="true"
    >
      <circle cx={6} cy={6} r={6} />
    </svg>
  )
}
