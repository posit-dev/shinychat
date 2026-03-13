import { createContext, useContext } from "react"
import type { ComponentType } from "react"

const ComponentMapContext = createContext<
  Record<string, ComponentType<unknown>>
>({})

export const ComponentMapProvider = ComponentMapContext.Provider
export const useComponentMap = () => useContext(ComponentMapContext)
