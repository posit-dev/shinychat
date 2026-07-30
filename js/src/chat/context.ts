import { createContext, useContext, type Dispatch } from "react"
import type { ShinyLifecycle, SlashCommandDef } from "../transport/types"
import type { ChatToolState, AnyAction, ToolGrouping } from "./state"
import { initialState } from "./state"
import type { StopScroll } from "use-stick-to-bottom"
import type { AttachmentPayload } from "./attachments"

export const ShinyLifecycleContext = createContext<ShinyLifecycle | null>(null)

export const ChatScrollContext = createContext<StopScroll | null>(null)

export function useChatStopScroll(): StopScroll | null {
  return useContext(ChatScrollContext)
}

// Nothing is superseded until a transcript exists to derive it from.
const initialToolState: ChatToolState = {
  supersededRequests: new Set(),
}

export const ChatToolContext = createContext<ChatToolState>(initialToolState)

export const ToolGroupingContext = createContext<ToolGrouping>(
  initialState.toolGrouping,
)

export function useToolGrouping(): ToolGrouping {
  return useContext(ToolGroupingContext)
}

export const ChatDispatchContext = createContext<Dispatch<AnyAction> | null>(
  null,
)

export type SubmitUserInput = (
  content: string,
  attachments: AttachmentPayload[],
) => void

export const ChatSubmitContext = createContext<SubmitUserInput | null>(null)

export const SlashCommandsContext = createContext<SlashCommandDef[]>([])

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

export function useChatSubmit(): SubmitUserInput {
  const ctx = useContext(ChatSubmitContext)
  if (ctx === null) {
    throw new Error(
      "useChatSubmit must be used within a ChatSubmitContext.Provider",
    )
  }
  return ctx
}

export function useSlashCommands(): SlashCommandDef[] {
  return useContext(SlashCommandsContext)
}
