import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"
import { Sidenote } from "./Sidenote"
import { SidenoteGroup } from "./SidenoteGroup"

export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
  "shiny-sidenote": Sidenote as ComponentType<unknown>,
  "shiny-sidenote-group": SidenoteGroup as ComponentType<unknown>,
}
