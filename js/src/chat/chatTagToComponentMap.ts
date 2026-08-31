import type { ComponentType } from "react"
import { Aside } from "./Aside"
import { AsideGroup, UntrustedAsideGroup } from "./AsideGroup"
import { EscapedIsland } from "../markdown/EscapedIsland"

// Trusted (html-typed or server-authored) content resolves custom element
// tags through this map. Tool requests and results are routed from
// structured wire blocks before Markdown rendering, so they no longer
// appear here.
export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
}

// Security: untrusted (model-authored) content must never resolve tool/web/
// island tags to live components — there is no sanitize step. A forged
// <shiny-tool-result value-type="html"> would reach innerHTML (stored XSS).
// All trust-gated tags render as inert text via EscapedIsland. The island
// entries are defense in depth beneath rehypeNeutralizeIslands and the
// primary guard on reparsed paths (e.g. aside popover body).
export const untrustedChatTagToComponentMap: Record<
  string,
  ComponentType<unknown>
> = {
  ...chatTagToComponentMap,
  // Asides stay resolvable (data carriers, not trust sinks), but the
  // popover body reparse must keep trust-gated tags escaped.
  "shiny-aside-group": UntrustedAsideGroup as ComponentType<unknown>,
  "shiny-chat-raw-html": EscapedIsland,
  "shinychat-raw-html": EscapedIsland,
  "shiny-tool-request": EscapedIsland,
  "shiny-tool-result": EscapedIsland,
  "shiny-web-activity": EscapedIsland,
  "shiny-web-search": EscapedIsland,
  "shiny-web-search-results": EscapedIsland,
  "shiny-web-fetch": EscapedIsland,
}
