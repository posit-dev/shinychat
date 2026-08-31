import type { ComponentType } from "react"
import { EscapedIsland } from "../markdown/EscapedIsland"

// Trust-gated tags that must never resolve to live components in untrusted
// (model-authored) content; they render as visible inert text instead.
export const trustGatedEscapes: Record<string, ComponentType<unknown>> = {
  "shiny-chat-raw-html": EscapedIsland,
  "shinychat-raw-html": EscapedIsland,
  "shiny-tool-request": EscapedIsland,
  "shiny-tool-result": EscapedIsland,
  "shiny-web-activity": EscapedIsland,
  "shiny-web-search": EscapedIsland,
  "shiny-web-search-results": EscapedIsland,
  "shiny-web-fetch": EscapedIsland,
}
