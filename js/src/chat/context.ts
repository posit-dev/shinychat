import { createContext, useContext, type Dispatch } from "react"
import type { ShinyLifecycle } from "../transport/types"
import type { ChatToolState, AnyAction } from "./state"
import { initialState } from "./state"

export const ShinyLifecycleContext = createContext<ShinyLifecycle | null>(null)

const initialToolState: ChatToolState = {
  hiddenToolRequests: initialState.hiddenToolRequests,
}

export const ChatToolContext = createContext<ChatToolState>(initialToolState)

export const ChatDispatchContext = createContext<Dispatch<AnyAction> | null>(
  null,
)

export function useShinyLifecycle(): ShinyLifecycle {
  const ctx = useContext(ShinyLifecycleContext)
  if (!ctx) {
    throw new Error(
      "useShinyLifecycle must be used within a ShinyLifecycleContext.Provider",
    )
  }
  return ctx
}

export function useChatToolState(): ChatToolState {
  return useContext(ChatToolContext)
}

export function useChatDispatch(): Dispatch<AnyAction> {
  const ctx = useContext(ChatDispatchContext)
  if (!ctx) {
    throw new Error(
      "useChatDispatch must be used within a ChatDispatchContext.Provider",
    )
  }
  return ctx
}
