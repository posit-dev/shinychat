import type { ComponentType } from "react"
import { toHtml } from "hast-util-to-html"
import type { Element } from "hast"

/** Renders a HAST element as inert text. Spoof guard for reserved tags in untrusted content. */
export const EscapedIsland = (({ node }: { node?: Element }) => (
  <>{node ? toHtml(node) : ""}</>
)) as ComponentType<unknown>
