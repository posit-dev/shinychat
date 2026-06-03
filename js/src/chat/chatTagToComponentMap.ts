import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"
import { WebActivity } from "./WebActivity"
import { Citation } from "./Citation"

// The web-activity carriers are consumed by <shiny-web-activity> (WebActivity
// reads their HAST data). Map them to the null Citation carrier so that, if one
// ever appears ungrouped, it renders nothing instead of a stray custom element.
export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
  "shiny-web-activity": WebActivity as ComponentType<unknown>,
  "shiny-web-search": Citation as ComponentType<unknown>,
  "shiny-web-search-results": Citation as ComponentType<unknown>,
  "shiny-web-fetch": Citation as ComponentType<unknown>,
  "shiny-citation": Citation as ComponentType<unknown>,
}
