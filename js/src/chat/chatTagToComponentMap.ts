import type { ComponentType } from "react"
import { Aside } from "./Aside"
import { AsideGroup, UntrustedAsideGroup } from "./AsideGroup"
import { EscapedIsland } from "../markdown/EscapedIsland"

export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
}

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

export const untrustedChatTagToComponentMap: Record<
  string,
  ComponentType<unknown>
> = {
  ...chatTagToComponentMap,
  "shiny-aside-group": UntrustedAsideGroup as ComponentType<unknown>,
  ...trustGatedEscapes,
}
