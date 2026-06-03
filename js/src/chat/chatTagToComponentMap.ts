import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"
import { WebSearch } from "./WebSearch"
import { WebFetch } from "./WebFetch"
import { Citation } from "./Citation"

export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
  "shiny-web-search": WebSearch as ComponentType<unknown>,
  "shiny-web-fetch": WebFetch as ComponentType<unknown>,
  "shiny-citation": Citation as ComponentType<unknown>,
}
