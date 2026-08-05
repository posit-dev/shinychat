import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"

// Complete tool elements are routed by routeToolBlocks before Markdown
// rendering. These bridges are fallback-only for incomplete or otherwise
// unrouted assistant elements, including content in greeting/thinking
// Markdown. Keep this map limited to fields with truthful leaf-card behavior:
// grouping and value-preview describe routed presentation, while
// custom-display deliberately renders nothing until the complete router path
// can preserve its standalone payload semantics.
export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
}
