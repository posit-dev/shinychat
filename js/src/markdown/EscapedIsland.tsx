import type { ComponentType } from "react"
import { toHtml } from "hast-util-to-html"
import type { Element } from "hast"

/**
 * Renders a HAST element as visible, inert text instead of live markup.
 * Used as a component-map backstop so that reserved elements (raw-HTML
 * islands, tool elements) appearing in untrusted content can never
 * instantiate their privileged React components.
 */
export const EscapedIsland = (({ node }: { node?: Element }) => (
  <>{node ? toHtml(node) : ""}</>
)) as ComponentType<unknown>
