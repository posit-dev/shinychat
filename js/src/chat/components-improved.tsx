import React, {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  useCallback,
  useImperativeHandle,
  forwardRef,
  useMemo,
  useReducer,
} from "react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import rehypeHighlight from "rehype-highlight"
import rehypeRaw from "rehype-raw"

import { renderDependencies, showShinyClientMessage } from "../utils/_utils"

import type { HtmlDep } from "../utils/_utils"

// Types
type ContentType = "markdown" | "semi-markdown" | "html" | "text"

type Message = {
  id: string
  content: string
  role: "user" | "assistant"
  content_type: ContentType
  chunk_type?: "message_start" | "message_end" | null
  icon?: string
  operation?: "append" | null
  streaming?: boolean
}

type UpdateUserInput = {
  value?: string
  placeholder?: string
  submit?: boolean
  focus?: boolean
}

type ChatState = {
  messages: Message[]
  inputDisabled: boolean
  placeholder: string
  iconAssistant: string
}

type ChatAction =
  | { type: "ADD_MESSAGE"; payload: Message }
  | {
      type: "UPDATE_LAST_MESSAGE"
      payload: { content: string; operation: "append" | "replace" }
    }
  | { type: "REMOVE_LOADING_MESSAGE" }
  | { type: "SET_INPUT_DISABLED"; payload: boolean }
  | { type: "SET_PLACEHOLDER"; payload: string }
  | { type: "CLEAR_MESSAGES" }
  | {
      type: "SET_MESSAGE_STREAMING"
      payload: { id: string; streaming: boolean }
    }

// Chat Context
const ChatContext = createContext<{
  state: ChatState
  dispatch: React.Dispatch<ChatAction>
  appendMessage: (message: Omit<Message, "id">) => void
  updateUserInput: (update: UpdateUserInput) => void
  inputRef: React.RefObject<ChatInputRef>
} | null>(null)

const useChatContext = () => {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error("useChatContext must be used within a ChatProvider")
  }
  return context
}

// Chat Reducer
const chatReducer = (state: ChatState, action: ChatAction): ChatState => {
  switch (action.type) {
    case "ADD_MESSAGE":
      return {
        ...state,
        messages: [
          ...state.messages,
          { ...action.payload, id: action.payload.id || `msg-${Date.now()}` },
        ],
        inputDisabled: true,
      }
    case "UPDATE_LAST_MESSAGE": {
      if (state.messages.length === 0) return state
      const newMessages = [...state.messages]
      const lastIndex = newMessages.length - 1
      const lastMessage = newMessages[lastIndex]
      if (lastMessage) {
        newMessages[lastIndex] = {
          ...lastMessage,
          content:
            action.payload.operation === "append"
              ? lastMessage.content + action.payload.content
              : action.payload.content,
        }
      }
      return { ...state, messages: newMessages }
    }
    case "REMOVE_LOADING_MESSAGE":
      return {
        ...state,
        messages: state.messages.filter(
          (msg, index) =>
            !(index === state.messages.length - 1 && msg.content.trim() === ""),
        ),
      }
    case "SET_INPUT_DISABLED":
      return { ...state, inputDisabled: action.payload }
    case "SET_PLACEHOLDER":
      return { ...state, placeholder: action.payload }
    case "CLEAR_MESSAGES":
      return { ...state, messages: [] }
    case "SET_MESSAGE_STREAMING":
      return {
        ...state,
        messages: state.messages.map((msg) =>
          msg.id === action.payload.id
            ? { ...msg, streaming: action.payload.streaming }
            : msg,
        ),
      }
    default:
      return state
  }
}

// Constants
const CHAT_CONTAINER_TAG = "shiny-chat-container"

const ICONS = {
  robot: "🤖",
  dots_fade: "⋯",
  send: "↑",
}

// Custom components for react-markdown
const MarkdownComponents = {
  table: ({ children, ...props }: React.HTMLProps<HTMLTableElement>) => (
    <table className="table table-striped table-bordered" {...props}>
      {children}
    </table>
  ),
  code: ({
    inline,
    className,
    children,
    ...props
  }: {
    inline?: boolean
    className?: string
    children?: React.ReactNode
  } & React.HTMLProps<HTMLElement>) => {
    const match = /language-(\w+)/.exec(className || "")
    const language = match ? match[1] : ""

    if (language === "html" && typeof children === "string") {
      // For {=html} blocks, render as raw HTML but safely
      return (
        <div
          className="raw-html-content"
          dangerouslySetInnerHTML={{ __html: children }}
        />
      )
    }

    return inline ? (
      <code className={className} {...props}>
        {children}
      </code>
    ) : (
      <div className="code-block-container">
        <button
          className="code-copy-button"
          onClick={() => navigator.clipboard?.writeText(String(children))}
          title="Copy to clipboard"
        >
          📋
        </button>
        <pre className={className} {...props}>
          <code>{children}</code>
        </pre>
      </div>
    )
  },
}

// MarkdownRenderer Component
interface MarkdownRendererProps {
  content: string
  contentType: ContentType
  streaming?: boolean
}

const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  contentType,
  streaming = false,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)

  // Handle Shiny bindings
  useEffect(() => {
    if (!containerRef.current) return

    const handleShinyBindings = async () => {
      const el = containerRef.current
      if (!el) return

      // Unbind first
      if (window?.Shiny?.unbindAll) {
        try {
          window.Shiny.unbindAll(el)
        } catch (err) {
          console.warn("Failed to unbind Shiny inputs/outputs:", err)
        }
      }

      // Then bind
      if (window?.Shiny?.initializeInputs && window?.Shiny?.bindAll) {
        try {
          window.Shiny.initializeInputs(el)
          await window.Shiny.bindAll(el)
        } catch (err) {
          console.warn("Failed to bind Shiny inputs/outputs:", err)
        }
      }
    }

    const timeoutId = setTimeout(handleShinyBindings, 100)
    return () => clearTimeout(timeoutId)
  }, [content])

  const renderedContent = useMemo(() => {
    if (contentType === "text") {
      return <pre className="text-content">{content}</pre>
    }

    if (contentType === "html") {
      return (
        <div
          className="html-content"
          dangerouslySetInnerHTML={{ __html: content }}
        />
      )
    }

    // For markdown and semi-markdown
    const isUserMessage = contentType === "semi-markdown"

    return (
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={isUserMessage ? [] : [rehypeHighlight, rehypeRaw]}
        components={isUserMessage ? {} : MarkdownComponents}
        className={`markdown-content ${isUserMessage ? "user-markdown" : "assistant-markdown"}`}
      >
        {content}
      </ReactMarkdown>
    )
  }, [content, contentType])

  return (
    <div ref={containerRef} className="markdown-renderer">
      {renderedContent}
      {streaming && (
        <span className="streaming-indicator">{ICONS.dots_fade}</span>
      )}
    </div>
  )
}

// ChatMessage Component
interface ChatMessageProps {
  message: Message
}

const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const { state } = useChatContext()

  const messageIcon = useMemo(() => {
    if (message.role !== "assistant") {
      return message.icon
    }

    const isEmpty = message.content.trim().length === 0
    return isEmpty
      ? ICONS.dots_fade
      : message.icon || state.iconAssistant || ICONS.robot
  }, [message.role, message.content, message.icon, state.iconAssistant])

  // Make suggestions accessible
  useEffect(() => {
    if (message.streaming) return

    const suggestions = document.querySelectorAll(
      ".suggestion,[data-suggestion]",
    )
    suggestions.forEach((el) => {
      if (!(el instanceof HTMLElement)) return
      if (el.hasAttribute("tabindex")) return

      el.setAttribute("tabindex", "0")
      el.setAttribute("role", "button")

      const suggestion = el.dataset.suggestion || el.textContent
      el.setAttribute("aria-label", `Use chat suggestion: ${suggestion}`)
    })
  }, [message.content, message.streaming])

  return (
    <div
      className={`chat-message chat-message--${message.role}`}
      data-message-id={message.id}
    >
      {messageIcon && (
        <div className="message-icon" aria-label={`${message.role} message`}>
          {messageIcon}
        </div>
      )}
      <div className="message-content">
        <MarkdownRenderer
          content={message.content}
          contentType={message.content_type}
          streaming={message.streaming}
        />
      </div>
    </div>
  )
}

// ChatInput Component
interface ChatInputSetInputOptions {
  submit?: boolean
  focus?: boolean
}

interface ChatInputProps {
  onInputSent: (content: string) => void
}

interface ChatInputRef {
  setInputValue: (value: string, options?: ChatInputSetInputOptions) => void
  focus: () => void
}

const ChatInput = forwardRef<ChatInputRef, ChatInputProps>(
  ({ onInputSent }, ref) => {
    const { state, dispatch } = useChatContext()
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const [isComposing, setIsComposing] = useState(false)
    const [value, setValue] = useState("")

    const valueIsEmpty = value.trim().length === 0

    const updateHeight = useCallback(() => {
      const el = textareaRef.current
      if (!el || el.scrollHeight === 0) return
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }, [])

    const onInput = useCallback(
      (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        setValue(e.target.value)
        updateHeight()
      },
      [updateHeight],
    )

    const sendInput = useCallback(
      (focus = true) => {
        if (valueIsEmpty || state.inputDisabled) return

        onInputSent(value)
        setValue("")

        if (focus && textareaRef.current) {
          textareaRef.current.focus()
        }
      },
      [valueIsEmpty, state.inputDisabled, value, onInputSent],
    )

    const onKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        const isEnter = e.code === "Enter" && !e.shiftKey
        if (isEnter && !isComposing && !valueIsEmpty) {
          e.preventDefault()
          sendInput()
        }
      },
      [isComposing, valueIsEmpty, sendInput],
    )

    const setInputValue = useCallback(
      (
        newValue: string,
        { submit = false, focus = false }: ChatInputSetInputOptions = {},
      ) => {
        const oldValue = value
        setValue(newValue)

        if (textareaRef.current) {
          textareaRef.current.value = newValue
          updateHeight()
        }

        if (submit) {
          setTimeout(() => {
            sendInput(false)
            if (oldValue) setInputValue(oldValue)
          }, 0)
        }

        if (focus && textareaRef.current) {
          textareaRef.current.focus()
        }
      },
      [value, sendInput, updateHeight],
    )

    const focusInput = useCallback(() => {
      textareaRef.current?.focus()
    }, [])

    useImperativeHandle(
      ref,
      () => ({
        setInputValue,
        focus: focusInput,
      }),
      [setInputValue, focusInput],
    )

    // Auto-resize on mount
    useEffect(() => {
      updateHeight()
    }, [updateHeight])

    return (
      <div
        className={`chat-input ${state.inputDisabled ? "chat-input--disabled" : ""}`}
      >
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          rows={1}
          placeholder={state.placeholder}
          value={value}
          onChange={onInput}
          onKeyDown={onKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          disabled={state.inputDisabled}
          data-shiny-no-bind-input
        />
        <button
          type="button"
          className="chat-input__send-button"
          title="Send message"
          aria-label="Send message"
          onClick={() => sendInput()}
          disabled={state.inputDisabled || valueIsEmpty}
        >
          {ICONS.send}
        </button>
      </div>
    )
  },
)

ChatInput.displayName = "ChatInput"

// ChatMessages Component
const ChatMessages: React.FC = () => {
  const { state } = useChatContext()
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [state.messages])

  return (
    <div className="chat-messages">
      {state.messages.map((message) => (
        <ChatMessage key={message.id} message={message} />
      ))}
      <div ref={messagesEndRef} />
    </div>
  )
}

// Main ChatApp Component
interface ChatAppProps {
  iconAssistant?: string
  id: string
}

interface ChatAppRef {
  updateUserInput: (update: UpdateUserInput) => void
}

const ChatApp = forwardRef<ChatAppRef, ChatAppProps>(
  ({ iconAssistant = "", id }, ref) => {
    const inputRef = useRef<ChatInputRef>(null)

    const initialState: ChatState = {
      messages: [],
      inputDisabled: false,
      placeholder: "Enter a message...",
      iconAssistant,
    }

    const [state, dispatch] = useReducer(chatReducer, initialState)

    const appendMessage = useCallback((message: Omit<Message, "id">) => {
      const fullMessage: Message = {
        ...message,
        id: `msg-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      }
      dispatch({ type: "ADD_MESSAGE", payload: fullMessage })
    }, [])

    const updateUserInput = useCallback((update: UpdateUserInput) => {
      const { value, placeholder, submit, focus } = update

      if (value !== undefined && inputRef.current) {
        inputRef.current.setInputValue(value, { submit, focus })
      }

      if (placeholder !== undefined) {
        dispatch({ type: "SET_PLACEHOLDER", payload: placeholder })
      }
    }, [])

    const onInputSent = useCallback(
      (content: string) => {
        // Add user message
        appendMessage({
          content,
          role: "user",
          content_type: "semi-markdown",
        })

        // Add loading message for assistant
        appendMessage({
          content: "",
          role: "assistant",
          content_type: "markdown",
        })

        // Notify Shiny
        if (window.Shiny?.setInputValue) {
          window.Shiny.setInputValue(`${id}-input`, content, {
            priority: "event",
          })
        }
      },
      [appendMessage, id],
    )

    useImperativeHandle(
      ref,
      () => ({
        updateUserInput,
      }),
      [updateUserInput],
    )

    // Handle Shiny events
    useEffect(() => {
      const handleInputSent = (event: Event) => {
        const customEvent = event as CustomEvent<Message>
        appendMessage(customEvent.detail)
        // Add loading message
        appendMessage({
          content: "",
          role: "assistant",
          content_type: "markdown",
        })
      }

      const handleAppend = (event: Event) => {
        const customEvent = event as CustomEvent<Message>
        appendMessage(customEvent.detail)
      }

      const handleAppendChunk = (event: Event) => {
        const customEvent = event as CustomEvent<Message>
        const message = customEvent.detail

        if (message.chunk_type === "message_start") {
          appendMessage(message)
          return
        }

        if (message.content !== undefined) {
          dispatch({
            type: "UPDATE_LAST_MESSAGE",
            payload: {
              content: message.content,
              operation: message.operation || "replace",
            },
          })
        }

        if (message.chunk_type === "message_end") {
          dispatch({ type: "SET_INPUT_DISABLED", payload: false })
        }
      }

      const handleClear = () => {
        dispatch({ type: "CLEAR_MESSAGES" })
      }

      const handleUpdateUserInput = (event: Event) => {
        const customEvent = event as CustomEvent<UpdateUserInput>
        updateUserInput(customEvent.detail)
      }

      const handleRemoveLoadingMessage = () => {
        dispatch({ type: "REMOVE_LOADING_MESSAGE" })
        dispatch({ type: "SET_INPUT_DISABLED", payload: false })
      }

      // Add event listeners
      document.addEventListener("shiny-chat-input-sent", handleInputSent)
      document.addEventListener("shiny-chat-append-message", handleAppend)
      document.addEventListener(
        "shiny-chat-append-message-chunk",
        handleAppendChunk,
      )
      document.addEventListener("shiny-chat-clear-messages", handleClear)
      document.addEventListener(
        "shiny-chat-update-user-input",
        handleUpdateUserInput,
      )
      document.addEventListener(
        "shiny-chat-remove-loading-message",
        handleRemoveLoadingMessage,
      )

      return () => {
        document.removeEventListener("shiny-chat-input-sent", handleInputSent)
        document.removeEventListener("shiny-chat-append-message", handleAppend)
        document.removeEventListener(
          "shiny-chat-append-message-chunk",
          handleAppendChunk,
        )
        document.removeEventListener("shiny-chat-clear-messages", handleClear)
        document.removeEventListener(
          "shiny-chat-update-user-input",
          handleUpdateUserInput,
        )
        document.removeEventListener(
          "shiny-chat-remove-loading-message",
          handleRemoveLoadingMessage,
        )
      }
    }, [appendMessage, updateUserInput])

    const contextValue = useMemo(
      () => ({
        state,
        dispatch,
        appendMessage,
        updateUserInput,
        inputRef,
      }),
      [state, appendMessage, updateUserInput],
    )

    return (
      <ChatContext.Provider value={contextValue}>
        <div className="chat-container">
          <ChatMessages />
          <ChatInput ref={inputRef} onInputSent={onInputSent} />
        </div>
      </ChatContext.Provider>
    )
  },
)

ChatApp.displayName = "ChatApp"

export { ChatApp, ChatMessage, ChatInput, MarkdownRenderer, ChatMessages }
export type { Message, UpdateUserInput, ChatAppRef }
