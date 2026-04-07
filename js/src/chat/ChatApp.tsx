import { useReducer, useEffect, useRef, useMemo, useCallback } from "react"
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
  type AnyAction,
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

  // Track streaming message content imperatively (not via React state)
  // so it's available immediately at chunk_end time, before React re-renders.
  const streamingRef = useRef<{
    role: "user" | "assistant"
    content: string
    contentType: "markdown" | "html" | "text"
  } | null>(null)

  // Wrap dispatch so that user-submitted messages (INPUT_SENT) also send
  // the message as an input value for server-side accumulation.
  const dispatchWithInput = useCallback(
    (action: AnyAction) => {
      dispatch(action)
      if (action.type === "INPUT_SENT") {
        transport.sendInput(`${elementId}_message`, {
          role: action.role,
          content: action.content,
          content_type: "markdown",
        } satisfies ChatMessageInput)
      }
    },
    [dispatch, transport, elementId],
  )

  // The textarea is fully uncontrolled, so value/focus mutations go through
  // the imperative handle rather than the reducer.
  useEffect(() => {
    const unsubscribe = transport.onMessage(elementId, (action) => {
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

      // Track streaming content imperatively so it's available at chunk_end
      // (React batches state updates, so stateRef would be stale).
      if (action.type === "chunk_start") {
        streamingRef.current = {
          role: action.message.role,
          content: action.message.content,
          contentType: action.message.content_type,
        }
      } else if (action.type === "chunk") {
        if (streamingRef.current) {
          if (action.operation === "replace") {
            streamingRef.current.content = action.content
          } else {
            streamingRef.current.content += action.content
          }
          if (action.content_type) {
            streamingRef.current.contentType = action.content_type
          }
        }
      } else if (action.type === "chunk_end") {
        if (streamingRef.current) {
          transport.sendInput(`${elementId}_message`, {
            role: streamingRef.current.role,
            content: streamingRef.current.content,
            content_type: streamingRef.current.contentType,
          } satisfies ChatMessageInput)
          streamingRef.current = null
        }
      } else if (action.type === "message") {
        // Non-streamed complete message
        const msg = action.message
        transport.sendInput(`${elementId}_message`, {
          role: msg.role,
          content: msg.content,
          content_type: msg.content_type,
        } satisfies ChatMessageInput)
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
        <ChatDispatchContext.Provider value={dispatchWithInput}>
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
