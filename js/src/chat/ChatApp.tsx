import { useReducer, useEffect, useRef, useMemo } from "react"
import {
  ShinyLifecycleContext,
  ChatToolContext,
  ChatDispatchContext,
} from "./context"
import {
  chatReducer,
  initialState,
  type ChatMessageData,
  type ChatToolState,
} from "./state"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
import type {
  ChatTransport,
  ShinyLifecycle,
  ChatMessageInput,
} from "../transport/types"

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
  const stateRef = useRef(state)
  stateRef.current = state

  // The textarea is fully uncontrolled, so value/focus mutations go through
  // the imperative handle rather than the reducer.
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
      // Bookmark save: serialize current messages and respond via sendInput
      if ((action as Record<string, unknown>).type === "_bookmark_save") {
        const bookmarkAction = action as unknown as {
          type: "_bookmark_save"
          key: string
        }
        const messages = stateRef.current.messages.map((msg) => ({
          role: msg.role,
          content: msg.content,
          content_type: msg.contentType,
        }))
        transport.sendInput(bookmarkAction.key, messages)
        return
      }

      if (action.type === "update_input") {
        // Placeholder updates go through the reducer (it's the only
        // remaining field the reducer tracks for update_input).
        if (action.placeholder !== undefined) {
          dispatch({ type: "update_input", placeholder: action.placeholder })
        }

        // Value and focus are always imperative — the textarea is
        // fully uncontrolled, so the reducer never touches its value.
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

      // After dispatching a completed message, send it as an input value
      // so the server can accumulate UI message state.
      if (action.type === "message") {
        const msg = action.message
        const input: ChatMessageInput = {
          role: msg.role,
          content: msg.content,
          content_type: msg.content_type,
        }
        transport.sendInput(`${elementId}_message`, input)
      } else if (action.type === "chunk_end") {
        // stateRef.current reflects state *before* dispatch (React batches),
        // so streamingMessage is still populated.
        const streaming = stateRef.current.streamingMessage
        if (streaming) {
          const input: ChatMessageInput = {
            role: streaming.role,
            content: streaming.content,
            content_type: streaming.contentType,
          }
          transport.sendInput(`${elementId}_message`, input)
        }
      }
    })
    return unsubscribe
  }, [transport, elementId])

  const toolState: ChatToolState = useMemo(
    () => ({
      hiddenToolRequests: state.hiddenToolRequests,
    }),
    [state.hiddenToolRequests],
  )

  return (
    <ShinyLifecycleContext.Provider value={shinyLifecycle}>
      <ChatToolContext.Provider value={toolState}>
        <ChatDispatchContext.Provider value={dispatch}>
          <ChatContainer
            ref={containerRef}
            transport={transport}
            messages={state.messages}
            streamingMessage={state.streamingMessage}
            inputDisabled={state.inputDisabled}
            inputPlaceholder={state.inputPlaceholder}
            iconAssistant={iconAssistant}
            inputId={inputId}
          />
        </ChatDispatchContext.Provider>
      </ChatToolContext.Provider>
    </ShinyLifecycleContext.Provider>
  )
}
