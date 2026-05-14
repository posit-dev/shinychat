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
  type GreetingData,
} from "./state"
import { ChatContainer, type ChatContainerHandle } from "./ChatContainer"
import type {
  ChatTransport,
  ShinyLifecycle,
  GreetingOptions,
} from "../transport/types"

interface InitialGreeting {
  content: string
  contentType: import("../transport/types").ContentType
  options: GreetingOptions
}

interface ChatAppProps {
  transport: ChatTransport
  shinyLifecycle: ShinyLifecycle
  elementId: string
  iconAssistant?: string
  inputId: string
  placeholder?: string
  initialMessages?: ChatMessageData[]
  initialGreeting?: InitialGreeting
}

function makeInitialGreeting(
  greeting: InitialGreeting,
  messagesLength: number,
): GreetingData {
  const dismissible = greeting.options.dismissible !== false
  const autoDismiss = dismissible && messagesLength > 0
  return {
    content: greeting.content,
    contentType: greeting.contentType,
    streaming: false,
    visible: !autoDismiss,
    dismissed: autoDismiss,
    dismissing: false,
    options: greeting.options,
    blocks: [
      {
        type: "content",
        content: greeting.content,
        contentType: greeting.contentType,
      },
    ],
  }
}

export function ChatApp({
  transport,
  shinyLifecycle,
  elementId,
  iconAssistant,
  inputId,
  placeholder,
  initialMessages,
  initialGreeting,
}: ChatAppProps) {
  const messages = initialMessages ?? []
  const [state, dispatch] = useReducer(chatReducer, {
    ...initialState,
    inputPlaceholder: placeholder ?? initialState.inputPlaceholder,
    messages,
    greeting: initialGreeting
      ? makeInitialGreeting(initialGreeting, messages.length)
      : null,
  })

  const containerRef = useRef<ChatContainerHandle>(null)

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
            greeting={state.greeting}
          />
        </ChatDispatchContext.Provider>
      </ChatToolContext.Provider>
    </ShinyLifecycleContext.Provider>
  )
}
