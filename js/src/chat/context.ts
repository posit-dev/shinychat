import { createContext, useContext, type Dispatch } from "react"
import type { ChatTransport, ShinyLifecycle } from "../transport/types"
import type { ChatState, AnyAction } from "./state"
import { initialState } from "./state"

export const TransportContext = createContext<ChatTransport | null>(null)

export const ShinyLifecycleContext = createContext<ShinyLifecycle | null>(null)

export const ChatStateContext = createContext<ChatState>(initialState)

export const ChatDispatchContext = createContext<Dispatch<AnyAction> | null>(
  null,
)

export function useTransport(): ChatTransport {
  const ctx = useContext(TransportContext)
  if (!ctx) {
    throw new Error(
      "useTransport must be used within a TransportContext.Provider",
    )
  }
  return ctx
}

export function useShinyLifecycle(): ShinyLifecycle {
  const ctx = useContext(ShinyLifecycleContext)
  if (!ctx) {
    throw new Error(
      "useShinyLifecycle must be used within a ShinyLifecycleContext.Provider",
    )
  }
  return ctx
}

export function useChatState(): ChatState {
  return useContext(ChatStateContext)
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
