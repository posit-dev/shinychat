import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"
import { Aside } from "./Aside"
import { AsideGroup } from "./AsideGroup"
import { WebActivityBridge } from "./WebActivity"
import { EscapedIsland } from "../markdown/EscapedIsland"

// Complete tool elements are routed by routeToolBlocks before Markdown
// rendering. These bridges are fallback-only for incomplete or otherwise
// unrouted elements in TRUSTED (html-typed or server-authored) content.
// Keep this map limited to fields with truthful leaf-card behavior:
// grouping and value-preview describe routed presentation, while
// custom-display deliberately renders nothing until the complete router path
// can preserve its standalone payload semantics.
export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
  "shiny-web-activity": WebActivityBridge as ComponentType<unknown>,
  "shiny-web-search": Aside as ComponentType<unknown>,
  "shiny-web-search-results": Aside as ComponentType<unknown>,
  "shiny-web-fetch": Aside as ComponentType<unknown>,
}

// Security: markdown-typed chat content is model-authored (untrusted), and
// thinking content is model-authored by definition. A forged
// <shiny-tool-result value-type="html"> in such content must never resolve
// to a tool bridge — its value would reach innerHTML (stored XSS). Route
// tool tags in untrusted content to EscapedIsland so they display as the
// literal markup the model wrote. The same holds for the web data carriers:
// a forged <shiny-web-search>/<shiny-web-fetch> must never group (via
// rehypeGroupWebActivity) into live web-activity chrome. Trusted content
// (html-typed blocks, greetings) keeps the full map above; the structured
// web_search/web_search_results/web_fetch blocks are the trusted channel.
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
