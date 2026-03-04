import { useReducer, useEffect } from "react"
import {
  TransportContext,
  ChatStateContext,
  ChatDispatchContext,
} from "./context"
import { chatReducer, initialState, type ChatMessageData } from "./state"
import { ChatContainer } from "./ChatContainer"
import type { ChatTransport } from "../transport/types"

interface ChatAppProps {
  transport: ChatTransport
  elementId: string
  iconAssistant?: string
  inputId: string
  placeholder?: string
  initialMessages?: ChatMessageData[]
}

export function ChatApp({
  transport,
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

  // Wire transport messages → dispatch
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
      if (action.type === "update_input" && action.submit) {
        // For submit: only dispatch placeholder to reducer (value is handled
        // imperatively by ChatContainer's transport listener to support
        // save/restore of the old textarea value)
        if (action.placeholder) {
          dispatch({ type: "update_input", placeholder: action.placeholder })
        }
        return
      }
      dispatch(action)
    })
    return unsubscribe
  }, [transport, elementId])

  return (
    <TransportContext.Provider value={transport}>
      <ChatStateContext.Provider value={state}>
        <ChatDispatchContext.Provider value={dispatch}>
          <ChatContainer
            iconAssistant={iconAssistant}
            inputId={inputId}
            elementId={elementId}
          />
        </ChatDispatchContext.Provider>
      </ChatStateContext.Provider>
    </TransportContext.Provider>
  )
}
