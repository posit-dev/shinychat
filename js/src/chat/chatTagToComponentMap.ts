import type { ComponentType } from "react"
import { Aside } from "./Aside"
import { AsideGroup } from "./AsideGroup"
import { EscapedIsland } from "../markdown/EscapedIsland"

// Trusted (html-typed or server-authored) content resolves custom element
// tags through this map. Tool requests and results are now routed exclusively
// from structured wire blocks (tool_request / tool_result) before Markdown
// rendering, so they no longer appear here. The remaining entries cover
// aside grouping, whose trusted-path behavior is still markup-driven.
export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
}

// Security: markdown-typed chat content is model-authored (untrusted), and
// thinking content is model-authored by definition. A forged
// <shiny-tool-result value-type="html"> in such content must never resolve
// to a tool bridge — its value would reach innerHTML (stored XSS). Route
// tool tags in untrusted content to EscapedIsland so they display as the
// literal markup the model wrote. The same holds for the web data carriers:
// a forged <shiny-web-search>/<shiny-web-fetch> must never resolve to live
// web-activity chrome. Trusted content (html-typed blocks, greetings) keeps
// the full map above; the structured web_search/web_search_results/web_fetch
// blocks are the trusted channel.
//
// The assistant markdownProcessor has NO rehypeSanitize step, so without
// these EscapedIsland entries the spoofed tags would render as real (empty)
// DOM elements and the literal-text checks would fail. They are load-bearing
// security guards.
export const untrustedChatTagToComponentMap: Record<
  string,
  ComponentType<unknown>
> = {
  ...chatTagToComponentMap,
  "shiny-tool-request": EscapedIsland,
  "shiny-tool-result": EscapedIsland,
  "shiny-web-activity": EscapedIsland,
  "shiny-web-search": EscapedIsland,
  "shiny-web-search-results": EscapedIsland,
  "shiny-web-fetch": EscapedIsland,
}
