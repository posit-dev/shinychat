import type { ComponentType } from "react"
import { ToolRequestBridge } from "./ToolRequestBridge"
import { ToolResultBridge } from "./ToolResultBridge"
import { Aside } from "./Aside"
import { AsideGroup } from "./AsideGroup"

export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-tool-request": ToolRequestBridge as ComponentType<unknown>,
  "shiny-tool-result": ToolResultBridge as ComponentType<unknown>,
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
}
