import React, {
  useEffect,
  useRef,
  useState,
  useCallback,
  useImperativeHandle,
  forwardRef,
} from "react"
import ClipboardJS from "clipboard"
import hljs from "highlight.js/lib/common"
import { Renderer, parse } from "marked"

import {
  createElement,
  createSVGIcon,
  renderDependencies,
  sanitizeHTML,
  showShinyClientMessage,
  throttle,
} from "../utils/_utils"

import type { HtmlDep } from "../utils/_utils"

type ContentType = "markdown" | "semi-markdown" | "html" | "text"

type Message = {
  content: string
  role: "user" | "assistant"
  content_type: ContentType
  chunk_type?: "message_start" | "message_end" | null
  icon?: string
  operation?: "append" | null
}

type UpdateUserInput = {
  value?: string
  placeholder?: string
  submit?: boolean
  focus?: boolean
}

const CHAT_CONTAINER_TAG = "shiny-chat-container"

const ICONS = {
  robot:
    '<svg fill="currentColor" class="bi bi-robot" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><path d="M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5M3 8.062C3 6.76 4.235 5.765 5.53 5.886a26.6 26.6 0 0 0 4.94 0C11.765 5.765 13 6.76 13 8.062v1.157a.93.93 0 0 1-.765.935c-.845.147-2.34.346-4.235.346s-3.39-.2-4.235-.346A.93.93 0 0 1 3 9.219zm4.542-.827a.25.25 0 0 0-.217.068l-.92.9a25 25 0 0 1-1.871-.183.25.25 0 0 0-.068.495c.55.076 1.232.149 2.02.193a.25.25 0 0 0 .189-.071l.754-.736.847 1.71a.25.25 0 0 0 .404.062l.932-.97a25 25 0 0 0 1.922-.188.25.25 0 0 0-.068-.495c-.538.074-1.207.145-1.98.189a.25.25 0 0 0-.166.076l-.754.785-.842-1.7a.25.25 0 0 0-.182-.135"/><path d="M8.5 1.866a1 1 0 1 0-1 0V3h-2A4.5 4.5 0 0 0 1 7.5V8a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1v-.5A4.5 4.5 0 0 0 10.5 3h-2zM14 7.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5A3.5 3.5 0 0 1 5.5 4h5A3.5 3.5 0 0 1 14 7.5"/></svg>',
  dots_fade:
    '<svg width="24" height="24" fill="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><style>.spinner_S1WN{animation:spinner_MGfb .8s linear infinite;animation-delay:-.8s}.spinner_Km9P{animation-delay:-.65s}.spinner_JApP{animation-delay:-.5s}@keyframes spinner_MGfb{93.75%,100%{opacity:.2}}</style><circle class="spinner_S1WN" cx="4" cy="12" r="3"/><circle class="spinner_S1WN spinner_Km9P" cx="12" cy="12" r="3"/><circle class="spinner_S1WN spinner_JApP" cx="20" cy="12" r="3"/></svg>',
}

// Markdown renderers
const markdownRenderer = new Renderer()
markdownRenderer.table = (header: string, body: string) => {
  return `<table class="table table-striped table-bordered">
      <thead>${header}</thead>
      <tbody>${body}</tbody>
    </table>`
}

const defaultMarkdownCodeRenderer = markdownRenderer.code
markdownRenderer.code = function (
  code: string,
  infostring: string | undefined,
  escaped: boolean,
): string {
  if (infostring === "{=html}") {
    return code
  }
  return defaultMarkdownCodeRenderer.call(this, code, infostring, escaped)
}

const semiMarkdownRenderer = new Renderer()
semiMarkdownRenderer.html = (html: string) =>
  html
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;")

function contentToHTML(content: string, contentType: ContentType): string {
  if (contentType === "markdown") {
    const html = parse(content, { renderer: markdownRenderer })
    return sanitizeHTML(html as string)
  } else if (contentType === "semi-markdown") {
    const html = parse(content, { renderer: semiMarkdownRenderer })
    return sanitizeHTML(html as string)
  } else if (contentType === "html") {
    return sanitizeHTML(content)
  } else if (contentType === "text") {
    return content
  } else {
    throw new Error(`Unknown content type: ${contentType}`)
  }
}

// SVG dot for streaming indicator
const SVG_DOT_CLASS = "markdown-stream-dot"
const SVG_DOT = createSVGIcon(
  `<svg width="12" height="12" xmlns="http://www.w3.org/2000/svg" class="${SVG_DOT_CLASS}" style="margin-left:.25em;margin-top:-.25em"><circle cx="6" cy="6" r="6"/></svg>`,
)

// MarkdownStream Component
interface MarkdownStreamProps {
  content: string
  contentType: ContentType
  streaming: boolean
  autoScroll: boolean
  onContentChange?: () => void
  onStreamEnd?: () => void
}

const MarkdownStream: React.FC<MarkdownStreamProps> = ({
  content,
  contentType,
  streaming,
  autoScroll,
  onContentChange,
  onStreamEnd,
}) => {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isContentBeingAdded, setIsContentBeingAdded] = useState(false)
  const [isUserScrolled, setIsUserScrolled] = useState(false)
  const [scrollableElement, setScrollableElement] =
    useState<HTMLElement | null>(null)

  const throttledBind = useCallback(
    (() => {
      let timeoutId: number | undefined
      return (el: HTMLElement) => {
        if (timeoutId) clearTimeout(timeoutId)
        timeoutId = window.setTimeout(() => doBind(el), 200)
      }
    })(),
    [],
  )

  const highlightAndCodeCopy = useCallback(() => {
    if (!containerRef.current) return
    const codeElements =
      containerRef.current.querySelectorAll<HTMLElement>("pre code")

    codeElements.forEach((el) => {
      if (el.dataset.highlighted === "yes") return

      hljs.highlightElement(el)

      const btn = createElement("button", {
        class: "code-copy-button",
        title: "Copy to clipboard",
      })
      btn.innerHTML = '<i class="bi"></i>'
      el.prepend(btn)

      const clipboard = new ClipboardJS(btn, { target: () => el })
      clipboard.on("success", (e) => {
        btn.classList.add("code-copy-button-checked")
        setTimeout(() => btn.classList.remove("code-copy-button-checked"), 2000)
        e.clearSelection()
      })
    })
  }, [])

  const appendStreamingDot = useCallback(() => {
    if (!containerRef.current) return
    removeStreamingDot()

    if (content.trim() === "") return
    if (
      containerRef.current.lastElementChild?.tagName.toLowerCase() ===
      "shiny-tool-request"
    )
      return

    const hasText = (node: Text): boolean => /\S/.test(node.textContent || "")
    const recurseInto = new Set(["p", "div", "pre", "ul", "ol"])
    const inlineContainers = new Set([
      "p",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "li",
      "code",
    ])

    const findInnermostStreamingElement = (element: Element): Element => {
      let current = element
      let depth = 0

      while (depth < 5) {
        depth++
        const children = current.childNodes
        let lastMeaningfulChild: Node | null = null

        for (let i = children.length - 1; i >= 0; i--) {
          const child = children[i]
          if (!child) break
          if (
            child.nodeType === Node.ELEMENT_NODE ||
            (child.nodeType === Node.TEXT_NODE && hasText(child as Text))
          ) {
            lastMeaningfulChild = child
            break
          }
        }

        if (!lastMeaningfulChild || !(lastMeaningfulChild instanceof Element)) {
          return current
        }

        const tagName = lastMeaningfulChild.tagName.toLowerCase()

        if (recurseInto.has(tagName)) {
          current = lastMeaningfulChild
          continue
        }

        return inlineContainers.has(tagName) ? lastMeaningfulChild : current
      }

      return current
    }

    findInnermostStreamingElement(containerRef.current).appendChild(
      SVG_DOT.cloneNode(true),
    )
  }, [content])

  const removeStreamingDot = useCallback(() => {
    if (!containerRef.current) return
    containerRef.current.querySelector(`svg.${SVG_DOT_CLASS}`)?.remove()
  }, [])

  const onScroll = useCallback(() => {
    if (!isContentBeingAdded) {
      setIsUserScrolled(!isNearBottom())
    }
  }, [isContentBeingAdded])

  const isNearBottom = useCallback((): boolean => {
    if (!scrollableElement) return false
    return (
      scrollableElement.scrollHeight -
        (scrollableElement.scrollTop + scrollableElement.clientHeight) <
      50
    )
  }, [scrollableElement])

  const findScrollableParent = useCallback((): HTMLElement | null => {
    if (!autoScroll || !containerRef.current) return null

    let el: HTMLElement | null = containerRef.current
    while (el) {
      if (el.scrollHeight > el.clientHeight) return el
      el = el.parentElement
      if (el?.tagName?.toLowerCase() === CHAT_CONTAINER_TAG.toLowerCase()) {
        break
      }
    }
    return null
  }, [autoScroll])

  const updateScrollableElement = useCallback(() => {
    const el = findScrollableParent()
    if (el !== scrollableElement) {
      scrollableElement?.removeEventListener("scroll", onScroll)
      setScrollableElement(el)
      el?.addEventListener("scroll", onScroll)
    }
  }, [findScrollableParent, scrollableElement, onScroll])

  const maybeScrollToBottom = useCallback(() => {
    if (!scrollableElement || isUserScrolled) return
    scrollableElement.scroll({
      top: scrollableElement.scrollHeight - scrollableElement.clientHeight,
      behavior: streaming ? "instant" : "smooth",
    })
  }, [scrollableElement, isUserScrolled, streaming])

  useEffect(() => {
    if (!containerRef.current) return

    setIsContentBeingAdded(true)
    doUnBind(containerRef.current)

    try {
      highlightAndCodeCopy()
    } catch (error) {
      console.warn("Failed to highlight code:", error)
    }

    if (streaming) {
      appendStreamingDot()
      throttledBind(containerRef.current)
    } else {
      doBind(containerRef.current)
    }

    updateScrollableElement()
    setIsContentBeingAdded(false)
    maybeScrollToBottom()

    if (onContentChange) {
      try {
        onContentChange()
      } catch (error) {
        console.warn("Failed to call onContentChange callback:", error)
      }
    }
  }, [
    content,
    highlightAndCodeCopy,
    streaming,
    appendStreamingDot,
    throttledBind,
    updateScrollableElement,
    maybeScrollToBottom,
    onContentChange,
  ])

  useEffect(() => {
    if (streaming) {
      appendStreamingDot()
    } else {
      removeStreamingDot()
      if (onStreamEnd) {
        try {
          onStreamEnd()
        } catch (error) {
          console.warn("Failed to call onStreamEnd callback:", error)
        }
      }
    }
  }, [streaming, appendStreamingDot, removeStreamingDot, onStreamEnd])

  useEffect(() => {
    return () => {
      scrollableElement?.removeEventListener("scroll", onScroll)
    }
  }, [scrollableElement, onScroll])

  const htmlContent = contentToHTML(content, contentType)

  return (
    <div ref={containerRef} dangerouslySetInnerHTML={{ __html: htmlContent }} />
  )
}

// ChatMessage Component
interface ChatMessageProps {
  content: string
  contentType: ContentType
  streaming: boolean
  icon?: string
  role: "user" | "assistant"
}

const ChatMessage: React.FC<ChatMessageProps> = ({
  content,
  contentType,
  streaming,
  icon = "",
  role,
}) => {
  const getIcon = useCallback(() => {
    if (role !== "assistant") {
      return icon
    }
    const isEmpty = content.trim().length === 0
    return isEmpty ? ICONS.dots_fade : icon || ICONS.robot
  }, [role, content, icon])

  const onContentChange = useCallback(() => {
    if (!streaming) makeSuggestionsAccessible()
  }, [streaming])

  const makeSuggestionsAccessible = useCallback(() => {
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
  }, [])

  const messageIcon = getIcon()

  return (
    <div className="chat-message" data-role={role}>
      {messageIcon && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: messageIcon }}
        />
      )}
      <MarkdownStream
        content={content}
        contentType={contentType}
        streaming={streaming}
        autoScroll={role === "assistant"}
        onContentChange={onContentChange}
        onStreamEnd={makeSuggestionsAccessible}
      />
    </div>
  )
}

// ChatInput Component
interface ChatInputSetInputOptions {
  submit?: boolean
  focus?: boolean
}

interface ChatInputProps {
  placeholder: string
  disabled: boolean
  id: string
  onInputSent: (content: string) => void
}

interface ChatInputRef {
  setInputValue: (value: string, options?: ChatInputSetInputOptions) => void
}

const ChatInput = forwardRef<ChatInputRef, ChatInputProps>(
  ({ placeholder, disabled, id, onInputSent }, ref) => {
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

    const onKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        const isEnter = e.code === "Enter" && !e.shiftKey
        if (isEnter && !isComposing && !valueIsEmpty) {
          e.preventDefault()
          sendInput()
        }
      },
      [isComposing, valueIsEmpty],
    )

    const sendInput = useCallback(
      (focus = true) => {
        if (valueIsEmpty || disabled) return

        if (window.Shiny?.setInputValue) {
          window.Shiny.setInputValue(id, value, { priority: "event" })
        }

        onInputSent(value)
        setValue("")

        if (focus && textareaRef.current) {
          textareaRef.current.focus()
        }
      },
      [valueIsEmpty, disabled, id, value, onInputSent],
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
          const inputEvent = new Event("input", {
            bubbles: true,
            cancelable: true,
          })
          textareaRef.current.dispatchEvent(inputEvent)
        }

        if (submit) {
          sendInput(false)
          if (oldValue) setInputValue(oldValue)
        }

        if (focus && textareaRef.current) {
          textareaRef.current.focus()
        }
      },
      [value, sendInput],
    )

    useImperativeHandle(
      ref,
      () => ({
        setInputValue,
      }),
      [setInputValue],
    )

    useEffect(() => {
      if (!textareaRef.current) return

      const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) updateHeight()
        })
      })

      observer.observe(textareaRef.current)
      return () => observer.disconnect()
    }, [updateHeight])

    const icon =
      '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" fill="currentColor" class="bi bi-arrow-up-circle-fill" viewBox="0 0 16 16"><path d="M16 8A8 8 0 1 0 0 8a8 8 0 0 0 16 0m-7.5 3.5a.5.5 0 0 1-1 0V5.707L5.354 7.854a.5.5 0 1 1-.708-.708l3-3a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1-.708.708L8.5 5.707z"/></svg>'

    return (
      <div className="chat-input" data-disabled={disabled}>
        <textarea
          ref={textareaRef}
          id={id}
          className="form-control"
          rows={1}
          placeholder={placeholder}
          value={value}
          onChange={onInput}
          onKeyDown={onKeyDown}
          onCompositionStart={() => setIsComposing(true)}
          onCompositionEnd={() => setIsComposing(false)}
          data-shiny-no-bind-input
          disabled={disabled}
        />
        <button
          type="button"
          title="Send message"
          aria-label="Send message"
          onClick={() => sendInput()}
          disabled={disabled || valueIsEmpty}
          dangerouslySetInnerHTML={{ __html: icon }}
        />
      </div>
    )
  },
)

ChatInput.displayName = "ChatInput"

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
    const [messages, setMessages] = useState<Message[]>([])
    const [inputProps, setInputProps] = useState({
      disabled: false,
      placeholder: "Enter a message...",
    })
    const inputRef = useRef<ChatInputRef>(null)

    const appendMessage = useCallback(
      (message: Message) => {
        if (iconAssistant && message.role === "assistant") {
          message.icon = message.icon || iconAssistant
        }

        setMessages((prev) => [
          ...prev,
          { ...message, id: `msg-${Date.now()}` },
        ])
        setInputProps((prev) => ({ ...prev, disabled: true }))
      },
      [iconAssistant],
    )

    const addLoadingMessage = useCallback(() => {
      const loadingMessage: Message = {
        content: "",
        role: "assistant" as const,
        content_type: "markdown" as const,
      }
      appendMessage(loadingMessage)
    }, [appendMessage])

    const removeLoadingMessage = useCallback(() => {
      setMessages((prev) => {
        if (prev.length === 0) return prev
        const lastMessage = prev[prev.length - 1]
        if (lastMessage && lastMessage.content.trim() === "") {
          return prev.slice(0, -1)
        }
        return prev
      })
    }, [])

    const updateLastMessage = useCallback(
      (content: string, operation: "append" | "replace" = "replace") => {
        setMessages((prev) => {
          if (prev.length === 0) return prev
          const newMessages = [...prev]
          const lastIndex = newMessages.length - 1
          const lastMessage = newMessages[lastIndex]

          if (lastMessage) {
            newMessages[lastIndex] = {
              ...lastMessage,
              content:
                operation === "append"
                  ? lastMessage.content + content
                  : content,
            }
          }

          return newMessages
        })
      },
      [],
    )

    const finalizeMessage = useCallback(() => {
      setInputProps((prev) => ({ ...prev, disabled: false }))
    }, [])

    const clearMessages = useCallback(() => {
      setMessages([])
    }, [])

    const updateUserInput = useCallback((update: UpdateUserInput) => {
      const { value, placeholder, submit, focus } = update
      if (value !== undefined && inputRef.current) {
        inputRef.current.setInputValue(value, { submit, focus })
      }
      if (placeholder !== undefined) {
        setInputProps((prev) => ({ ...prev, placeholder }))
      }
    }, [])

    const onInputSent = useCallback(
      (content: string) => {
        const userMessage: Message = {
          content,
          role: "user" as const,
          content_type: "semi-markdown" as const,
        }
        appendMessage(userMessage)
        addLoadingMessage()
      },
      [appendMessage, addLoadingMessage],
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
        addLoadingMessage()
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
          updateLastMessage(message.content, message.operation || "replace")
        }

        if (message.chunk_type === "message_end") {
          finalizeMessage()
        }
      }

      const handleClear = () => clearMessages()

      const handleUpdateUserInput = (event: Event) => {
        const customEvent = event as CustomEvent<UpdateUserInput>
        updateUserInput(customEvent.detail)
      }

      const handleRemoveLoadingMessage = () => {
        removeLoadingMessage()
        finalizeMessage()
      }

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
    }, [
      appendMessage,
      addLoadingMessage,
      updateLastMessage,
      finalizeMessage,
      clearMessages,
      updateUserInput,
      removeLoadingMessage,
    ])

    return (
      <div className="chat-container">
        <div className="chat-messages">
          {messages.map((message, index) => (
            <ChatMessage
              key={`${index}-${message.content.slice(0, 10)}`}
              content={message.content}
              contentType={message.content_type}
              streaming={false} // Will be handled by chunk events
              icon={message.icon}
              role={message.role}
            />
          ))}
        </div>
        <ChatInput
          ref={inputRef}
          placeholder={inputProps.placeholder}
          disabled={inputProps.disabled}
          id={`${id}-input`}
          onInputSent={onInputSent}
        />
      </div>
    )
  },
)

ChatApp.displayName = "ChatApp"

// Shiny binding functions
async function doUnBind(el: HTMLElement): Promise<void> {
  if (!window?.Shiny?.unbindAll) return
  try {
    window.Shiny.unbindAll(el)
  } catch (err) {
    showShinyClientMessage({
      status: "error",
      message: `Failed to unbind Shiny inputs/outputs: ${err}`,
    })
  }
}

async function doBind(el: HTMLElement): Promise<void> {
  if (!window?.Shiny?.initializeInputs) return
  if (!window?.Shiny?.bindAll) return

  try {
    window.Shiny.initializeInputs(el)
  } catch (err) {
    showShinyClientMessage({
      status: "error",
      message: `Failed to initialize Shiny inputs: ${err}`,
    })
  }

  try {
    await window.Shiny.bindAll(el)
  } catch (err) {
    showShinyClientMessage({
      status: "error",
      message: `Failed to bind Shiny inputs/outputs: ${err}`,
    })
  }
}

export { ChatApp, ChatMessage, ChatInput, MarkdownStream }
export type { Message, UpdateUserInput, ChatAppRef }
