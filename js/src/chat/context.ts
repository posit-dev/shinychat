import { createContext, useContext, type Dispatch } from "react"
import type { ChatTransport } from "../transport/types"
import type { ChatState, AnyAction } from "./state"
import { initialState } from "./state"

export const TransportContext = createContext<ChatTransport>(
  null as unknown as ChatTransport,
)

export const ChatStateContext = createContext<ChatState>(initialState)

export const ChatDispatchContext = createContext<Dispatch<AnyAction>>(
  null as unknown as Dispatch<AnyAction>,
)

export function useTransport(): ChatTransport {
  return useContext(TransportContext)
}

export function useChatState(): ChatState {
  return useContext(ChatStateContext)
}

export function useChatDispatch(): Dispatch<AnyAction> {
  return useContext(ChatDispatchContext)
}
