import { useReducer, useEffect } from "react"
import { TransportContext, ChatStateContext, ChatDispatchContext } from "./context"
import { chatReducer, initialState } from "./state"
import { ChatContainer } from "./ChatContainer"
import type { ChatTransport } from "../transport/types"

interface ChatAppProps {
  transport: ChatTransport
  elementId: string
  iconAssistant?: string
  inputId: string
  placeholder?: string
}

export function ChatApp({
  transport,
  elementId,
  iconAssistant,
  inputId,
  placeholder,
}: ChatAppProps) {
  const [state, dispatch] = useReducer(chatReducer, {
    ...initialState,
    inputPlaceholder: placeholder ?? initialState.inputPlaceholder,
  })

  // Wire transport messages → dispatch
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
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
          />
        </ChatDispatchContext.Provider>
      </ChatStateContext.Provider>
    </TransportContext.Provider>
  )
}
