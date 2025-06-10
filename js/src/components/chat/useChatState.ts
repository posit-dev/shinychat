import { useState, useCallback } from "preact/hooks"
import type { Message, UpdateUserInput } from "./types"

export interface ChatState {
  // State
  messages: Message[]
  inputValue: string
  inputDisabled: boolean

  // Message operations (for Shiny integration)
  appendMessage: (message: Message) => void
  appendMessageChunk: (message: Message) => void
  clearMessages: () => void
  removeLoadingMessage: () => void
  updateUserInput: (update: UpdateUserInput) => void

  // UI operations
  handleInputSent: (
    value: string,
    onSendMessage?: (message: Message) => void,
  ) => void
  setInputValue: (value: string) => void
  setInputDisabled: (disabled: boolean) => void
}

export function useChatState(initialMessages: Message[] = []): ChatState {
  const [messages, setMessages] = useState<Message[]>(initialMessages)
  const [inputValue, setInputValue] = useState("")
  const [inputDisabled, setInputDisabled] = useState(false)

  // Core message operations
  const appendMessage = useCallback((message: Message) => {
    setMessages((prev) => [...prev, message])
    setInputDisabled(false)
  }, [])

  const appendMessageChunk = useCallback((message: Message) => {
    setMessages((prev) => {
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
            ? (lastMessage?.content || "") + message.content
            : message.content

        newMessages[lastIndex] = {
          role: message.role,
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
    setMessages([])
    setInputDisabled(false)
  }, [])

  const removeLoadingMessage = useCallback(() => {
    setMessages((prev) => prev.filter((msg) => msg.content.trim() !== ""))
    setInputDisabled(false)
  }, [])

  // Input operations
  const updateUserInput = useCallback((update: UpdateUserInput) => {
    if (update.value !== undefined) {
      setInputValue(update.value)
    }
    if (update.submit) {
      // This would trigger a submit, but we need the onSendMessage callback
      // We'll handle this in the component level
    }
    if (update.focus) {
      // Focus handling will be done at component level
    }
  }, [])

  const handleInputSent = useCallback(
    (value: string, onSendMessage?: (message: Message) => void) => {
      const userMessage: Message = {
        content: value,
        role: "user",
        id: `user-${Date.now()}`,
      }

      if (onSendMessage) {
        // External control - notify parent
        onSendMessage(userMessage)
      } else {
        // Internal control - manage state ourselves
        appendMessage(userMessage)

        // Add loading message for assistant response
        const loadingMessage: Message = {
          content: "",
          role: "assistant",
          id: `loading-${Date.now()}`,
        }
        setMessages((prev) => [...prev, loadingMessage])
      }

      // Always clear input and disable it
      setInputValue("")
      setInputDisabled(true)
    },
    [appendMessage],
  )

  const setInputValueCallback = useCallback((value: string) => {
    setInputValue(value)
  }, [])

  const setInputDisabledCallback = useCallback((disabled: boolean) => {
    setInputDisabled(disabled)
  }, [])

  return {
    // State
    messages,
    inputValue,
    inputDisabled,

    // Message operations (for Shiny integration)
    appendMessage,
    appendMessageChunk,
    clearMessages,
    removeLoadingMessage,
    updateUserInput,

    // UI operations
    handleInputSent,
    setInputValue: setInputValueCallback,
    setInputDisabled: setInputDisabledCallback,
  }
}
