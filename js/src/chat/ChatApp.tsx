import { useReducer, useEffect, useRef } from "react"
import {
  TransportContext,
  ShinyLifecycleContext,
  ChatStateContext,
  ChatDispatchContext,
} from "./context"
import { chatReducer, initialState, type ChatMessageData } from "./state"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
import type { ChatTransport, ShinyLifecycle } from "../transport/types"

interface ChatAppProps {
  transport: ChatTransport
  shinyLifecycle: ShinyLifecycle
  elementId: string
  iconAssistant?: string
  inputId: string
  placeholder?: string
  initialMessages?: ChatMessageData[]
}

export function ChatApp({
  transport,
  shinyLifecycle,
  elementId,
  iconAssistant,
  inputId,
  placeholder,
  initialMessages,
}: ChatAppProps) {
  const [state, dispatch] = useReducer(chatReducer, {
    ...initialState,
    inputPlaceholder: placeholder ?? initialState.inputPlaceholder,
    messages: initialMessages ?? [],
  })

  const containerRef = useRef<ChatContainerHandle>(null)

  // Single transport subscription: routes actions to the reducer and handles
  // imperative input commands (submit/focus) via the container ref.
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
      if (action.type === "update_input" && (action.submit || action.focus)) {
        // Imperative actions need direct ChatInput access (save/restore value,
        // focus management). Dispatch only the placeholder update to the reducer.
        if (action.placeholder) {
          dispatch({ type: "update_input", placeholder: action.placeholder })
        }

        if (action.value !== undefined) {
          containerRef.current?.setInputValue(action.value, {
            submit: action.submit,
            focus: action.focus,
          })
        } else if (action.focus) {
          containerRef.current?.focus()
        }
        return
      }
      dispatch(action)
    })
    return unsubscribe
  }, [transport, elementId])

  return (
    <TransportContext.Provider value={transport}>
      <ShinyLifecycleContext.Provider value={shinyLifecycle}>
        <ChatStateContext.Provider value={state}>
          <ChatDispatchContext.Provider value={dispatch}>
            <ChatContainer
              ref={containerRef}
              iconAssistant={iconAssistant}
              inputId={inputId}
            />
          </ChatDispatchContext.Provider>
        </ChatStateContext.Provider>
      </ShinyLifecycleContext.Provider>
    </TransportContext.Provider>
  )
}
