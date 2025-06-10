import { useEffect, useRef, useState, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import { ChatInput } from "./ChatInput"
import { ChatMessages } from "./ChatMessages"
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
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const [internalMessages, setInternalMessages] = useState<Message[]>([])
  const [inputDisabled, setInputDisabled] = useState(disabled)
  const [inputValue, setInputValue] = useState("")

  // Use external messages if provided, otherwise use internal state
  const messages =
    externalMessages.length > 0 ? externalMessages : internalMessages

  // Handle input ref callback
  const handleInputRef = useCallback((element: HTMLTextAreaElement | null) => {
    inputRef.current = element
  }, [])

  // Handle input sent
  const handleInputSent = useCallback(
    (value: string) => {
      const userMessage: Message = {
        content: value,
        role: "user",
      }

      // If using external messages, notify parent
      if (externalMessages.length > 0) {
        onSendMessage?.(userMessage)
      } else {
        // Otherwise manage internal state
        setInternalMessages((prev) => [...prev, userMessage])
        // Add loading message
        const loadingMessage: Message = {
          content: "",
          role: "assistant",
          id: `loading-${Date.now()}`,
        }
        setInternalMessages((prev) => [...prev, loadingMessage])
      }

      setInputDisabled(true)
    },
    [externalMessages.length, onSendMessage],
  )

  // Handle suggestion clicks
  const handleSuggestionClick = useCallback((e: MouseEvent) => {
    handleSuggestionEvent(e)
  }, [])

  const handleSuggestionKeydown = useCallback((e: KeyboardEvent) => {
    const isEnterOrSpace = e.key === "Enter" || e.key === " "
    if (!isEnterOrSpace) return
    handleSuggestionEvent(e)
  }, [])

  const handleSuggestionEvent = (e: MouseEvent | KeyboardEvent) => {
    const { suggestion, submit } = getSuggestion(e.target)
    if (!suggestion) return

    e.preventDefault()

    // Cmd/Ctrl + (event) = force submitting
    // Alt/Opt + (event) = force setting without submitting
    const shouldSubmit =
      e.metaKey || e.ctrlKey ? true : e.altKey ? false : submit || false

    if (onSuggestionClick) {
      onSuggestionClick(suggestion, shouldSubmit)
    } else {
      // Handle suggestion internally
      const textarea = inputRef.current
      if (textarea && (textarea as any).setInputValue) {
        ;(textarea as any).setInputValue(suggestion, {
          submit: shouldSubmit,
          focus: !shouldSubmit,
        })
      }
    }
  }

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

  // Public methods for external control
  const appendMessage = useCallback((message: Message) => {
    setInternalMessages((prev) => [...prev, message])
    setInputDisabled(false)
  }, [])

  const appendMessageChunk = useCallback((message: Message) => {
    setInternalMessages((prev) => {
      const newMessages = [...prev]

      if (message.chunk_type === "message_start") {
        // Remove loading message and add new streaming message
        const filteredMessages = newMessages.filter(
          (msg) => msg.content.trim() !== "",
        )
        return [
          ...filteredMessages,
          { ...message, id: `streaming-${Date.now()}` },
        ]
      }

      // Update last message
      if (newMessages.length > 0) {
        const lastIndex = newMessages.length - 1
        const lastMessage = newMessages[lastIndex]

        const content =
          message.operation === "append"
            ? lastMessage.content + message.content
            : message.content

        newMessages[lastIndex] = {
          ...lastMessage,
          content,
          chunk_type: message.chunk_type,
        }

        if (message.chunk_type === "message_end") {
          setInputDisabled(false)
        }
      }

      return newMessages
    })
  }, [])

  const clearMessages = useCallback(() => {
    setInternalMessages([])
  }, [])

  const updateUserInput = useCallback(
    ({
      value,
      placeholder: newPlaceholder,
      submit,
      focus,
    }: UpdateUserInput) => {
      if (value !== undefined) {
        const textarea = inputRef.current
        if (textarea && (textarea as any).setInputValue) {
          ;(textarea as any).setInputValue(value, { submit, focus })
        }
      }
      // Note: placeholder update would need to be handled by parent component
    },
    [],
  )

  const removeLoadingMessage = useCallback(() => {
    setInternalMessages((prev) =>
      prev.filter((msg) => msg.content.trim() !== ""),
    )
    setInputDisabled(false)
  }, [])

  // Setup intersection observer for input shadow
  useEffect(() => {
    const sentinel = sentinelRef.current
    if (!sentinel) return

    const observer = new IntersectionObserver(
      (entries) => {
        const textarea = inputRef.current
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

  // Setup event listeners
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

  // Expose public methods via ref
  useEffect(() => {
    if (containerRef.current) {
      ;(containerRef.current as any).appendMessage =
        appendMessage(containerRef.current as any).appendMessageChunk =
        appendMessageChunk(containerRef.current as any).clearMessages =
        clearMessages(containerRef.current as any).updateUserInput =
        updateUserInput(containerRef.current as any).removeLoadingMessage =
          removeLoadingMessage
    }
  }, [
    appendMessage,
    appendMessageChunk,
    clearMessages,
    updateUserInput,
    removeLoadingMessage,
  ])

  return (
    <div ref={containerRef} id={id} className="chat-container">
      <ChatMessages messages={messages} iconAssistant={iconAssistant} />

      <div ref={sentinelRef} style={{ width: "100%", height: "0px" }} />

      <ChatInput
        inputRef={handleInputRef}
        placeholder={placeholder}
        disabled={inputDisabled}
        value={inputValue}
        onValueChange={setInputValue}
        onInputSent={handleInputSent}
      />
    </div>
  )
}
