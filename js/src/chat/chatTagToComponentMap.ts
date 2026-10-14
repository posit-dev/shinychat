import type { ComponentType } from "react"
import { Aside } from "./Aside"
import { AsideGroup, UntrustedAsideGroup } from "./AsideGroup"
import { trustGatedEscapes } from "./trustGatedEscapes"

export const chatTagToComponentMap: Record<string, ComponentType<unknown>> = {
  "shiny-aside": Aside as ComponentType<unknown>,
  "shiny-aside-group": AsideGroup as ComponentType<unknown>,
}

export const untrustedChatTagToComponentMap: Record<
  string,
  ComponentType<unknown>
> = {
  ...chatTagToComponentMap,
  "shiny-aside-group": UntrustedAsideGroup as ComponentType<unknown>,
  ...trustGatedEscapes,
}
