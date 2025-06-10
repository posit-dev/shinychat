import { useEffect, useRef, useState, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import { ChatInput, ChatInputMethods } from "./ChatInput"
import { ChatMessages } from "./ChatMessages"
import { useChatState } from "./useChatState"
import type { Message, UpdateUserInput } from "./types"

export interface ChatContainerProps {
  id?: string
  messages?: Message[]
  iconAssistant?: string
  placeholder?: string
  disabled?: boolean
  onSendMessage?: (message: Message) => void
  onSuggestionClick?: (suggestion: string, submit: boolean) => void
}

export function ChatContainer({
  id,
  messages: externalMessages = [],
  iconAssistant = "",
  placeholder = "Enter a message...",
  disabled = false,
  onSendMessage,
  onSuggestionClick,
}: ChatContainerProps): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const [inputMethods, setInputMethods] = useState<ChatInputMethods | null>(
    null,
  )

  // Use the custom hook for state management
  const chat = useChatState()

  // Use external messages if provided, otherwise use hook's internal state
  const messages =
    externalMessages.length > 0 ? externalMessages : chat.messages

  // Handle input sent - either external control or internal
  const handleInputSent = useCallback(
    (value: string) => {
      if (externalMessages.length > 0) {
        // External control - notify parent, don't modify internal state
        const userMessage: Message = { content: value, role: "user" }
        onSendMessage?.(userMessage)
      } else {
        // Internal control - use hook
        chat.handleInputSent(value)
      }
    },
    [externalMessages.length, onSendMessage, chat],
  )

  // Shiny Integration: Listen for CustomEvents
  useEffect(() => {
    const container = containerRef.current
    if (!container || !id) return

    // Event handlers that call hook methods
    const handleAppendMessage = (e: CustomEvent<Message>) => {
      chat.appendMessage(e.detail)
    }

    const handleAppendChunk = (e: CustomEvent<Message>) => {
      chat.appendMessageChunk(e.detail)
    }

    const handleClearMessages = () => {
      chat.clearMessages()
    }

    const handleUpdateInput = (e: CustomEvent<UpdateUserInput>) => {
      const update = e.detail
      chat.updateUserInput(update)

      // Handle focus and submit options
      if (inputMethods) {
        if (update.submit && update.value) {
          inputMethods.setInputValue(update.value, { submit: true })
        }
        if (update.focus) {
          inputMethods.focus()
        }
      }
    }

    const handleRemoveLoading = () => {
      chat.removeLoadingMessage()
    }

    // Add event listeners for Shiny integration
    container.addEventListener(
      "shiny-chat-append-message",
      handleAppendMessage as EventListener,
    )
    container.addEventListener(
      "shiny-chat-append-message-chunk",
      handleAppendChunk as EventListener,
    )
    container.addEventListener("shiny-chat-clear-messages", handleClearMessages)
    container.addEventListener(
      "shiny-chat-update-user-input",
      handleUpdateInput as EventListener,
    )
    container.addEventListener(
      "shiny-chat-remove-loading-message",
      handleRemoveLoading,
    )

    return () => {
      container.removeEventListener(
        "shiny-chat-append-message",
        handleAppendMessage as EventListener,
      )
      container.removeEventListener(
        "shiny-chat-append-message-chunk",
        handleAppendChunk as EventListener,
      )
      container.removeEventListener(
        "shiny-chat-clear-messages",
        handleClearMessages,
      )
      container.removeEventListener(
        "shiny-chat-update-user-input",
        handleUpdateInput as EventListener,
      )
      container.removeEventListener(
        "shiny-chat-remove-loading-message",
        handleRemoveLoading,
      )
    }
  }, [id, chat, inputMethods])

  const handleSuggestionEvent = useCallback(
    (e: MouseEvent | KeyboardEvent) => {
      const { suggestion, submit } = getSuggestion(e.target)
      if (!suggestion) return

      e.preventDefault()

      // Cmd/Ctrl + (event) = force submitting
      // Alt/Opt + (event) = force setting without submitting
      const shouldSubmit =
        e.metaKey || e.ctrlKey ? true : e.altKey ? false : submit || false

      if (onSuggestionClick) {
        onSuggestionClick(suggestion, shouldSubmit)
      } else if (inputMethods) {
        // Handle suggestion internally using input methods
        inputMethods.setInputValue(suggestion, {
          submit: shouldSubmit,
          focus: !shouldSubmit,
        })
      }
    },
    [inputMethods, onSuggestionClick],
  )

  // Handle suggestion clicks
  const handleSuggestionClick = useCallback(
    (e: MouseEvent) => {
      handleSuggestionEvent(e)
    },
    [handleSuggestionEvent],
  )

  const handleSuggestionKeydown = useCallback(
    (e: KeyboardEvent) => {
      const isEnterOrSpace = e.key === "Enter" || e.key === " "
      if (!isEnterOrSpace) return
      handleSuggestionEvent(e)
    },
    [handleSuggestionEvent],
  )

  const getSuggestion = (
    target: EventTarget | null,
  ): { suggestion?: string; submit?: boolean } => {
    if (!(target instanceof HTMLElement)) return {}

    const el = target.closest(".suggestion, [data-suggestion]")
    if (!(el instanceof HTMLElement)) return {}

    const isSuggestion =
      el.classList.contains("suggestion") || el.dataset.suggestion !== undefined
    if (!isSuggestion) return {}

    const suggestion = el.dataset.suggestion || el.textContent

    return {
      suggestion: suggestion || undefined,
      submit:
        el.classList.contains("submit") ||
        el.dataset.suggestionSubmit === "" ||
        el.dataset.suggestionSubmit === "true",
    }
  }

  // Setup intersection observer for input shadow
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        const container = containerRef.current
        if (!container) return

        // Find the textarea in the chat input
        const textarea = container.querySelector(
          ".chat-input textarea",
        ) as HTMLTextAreaElement
        if (!textarea) return

        const addShadow = entries[0]?.intersectionRatio === 0
        textarea.classList.toggle("shadow", addShadow)
      },
      {
        threshold: [0, 1],
        rootMargin: "0px",
      },
    )

    observer.observe(sentinel)

    return () => observer.disconnect()
  }, [])

  // Setup event listeners for suggestions
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    container.addEventListener("click", handleSuggestionClick as EventListener)
    container.addEventListener(
      "keydown",
      handleSuggestionKeydown as EventListener,
    )

    return () => {
      container.removeEventListener(
        "click",
        handleSuggestionClick as EventListener,
      )
      container.removeEventListener(
        "keydown",
        handleSuggestionKeydown as EventListener,
      )
    }
  }, [handleSuggestionClick, handleSuggestionKeydown])

  return (
    <div ref={containerRef} id={id} className="chat-container">
      <ChatMessages messages={messages} iconAssistant={iconAssistant} />

      <div ref={sentinelRef} style={{ width: "100%", height: "0px" }} />

      <ChatInput
        placeholder={placeholder}
        disabled={disabled || chat.inputDisabled}
        value={chat.inputValue}
        onValueChange={chat.setInputValue}
        onInputSent={handleInputSent}
        onMethodsReady={setInputMethods}
      />
    </div>
  )
}
