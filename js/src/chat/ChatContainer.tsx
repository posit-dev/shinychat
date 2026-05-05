import {
  useState,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react"
import { createPortal } from "react-dom"
import { useStickToBottom } from "use-stick-to-bottom"
import { ChatMessages } from "./ChatMessages"
import { ChatMessage } from "./ChatMessage"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import { ChatInput, type ChatInputHandle } from "./ChatInput"
import { ScrollToBottomButton } from "./ScrollToBottomButton"
import { ExternalLinkDialogComponent } from "./ExternalLinkDialog"
import type { ChatMessageData } from "./state"
import type { ChatTransport } from "../transport/types"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

export interface ChatContainerProps {
  transport: ChatTransport
  messages: ChatMessageData[]
  streamingMessage: ChatMessageData | null
  inputDisabled: boolean
  inputPlaceholder: string
  iconAssistant?: string
  inputId: string
}

export type ChatContainerHandle = ChatInputHandle

export const ChatContainer = forwardRef<
  ChatContainerHandle,
  ChatContainerProps
>(function ChatContainer(
  {
    transport,
    messages,
    streamingMessage,
    inputDisabled,
    inputPlaceholder,
    iconAssistant,
    inputId,
  },
  ref,
) {
  const chatInputRef = useRef<ChatInputHandle>(null)

  const [pendingUrl, setPendingUrl] = useState<string | null>(null)
  const pendingUrlRef = useRef<string | null>(null)
  pendingUrlRef.current = pendingUrl

  const { scrollRef, contentRef, isAtBottom, scrollToBottom } =
    useStickToBottom({ resize: "smooth" })

  useImperativeHandle(ref, () => ({
    setInputValue(...args) {
      chatInputRef.current?.setInputValue(...args)
    },
    focus() {
      chatInputRef.current?.focus()
    },
  }))

  const onContainerClick = useCallback((e: React.MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement
    const linkEl = target.closest(
      "a[data-external-link]",
    ) as HTMLAnchorElement | null
    if (!linkEl || !linkEl.href) return

    e.preventDefault()

    if (window.shinychat_always_open_external_links) {
      window.open(linkEl.href, "_blank", "noopener,noreferrer")
      return
    }

    if (typeof window.HTMLDialogElement === "undefined") {
      window.open(linkEl.href, "_blank", "noopener,noreferrer")
      return
    }

    setPendingUrl(linkEl.href)
  }, [])

  function getSuggestion(target: EventTarget | null): {
    suggestion?: string
    submit?: boolean
  } {
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

  function handleSuggestionEvent(
    e: React.MouseEvent | React.KeyboardEvent,
  ): void {
    const { suggestion, submit } = getSuggestion(e.target)
    if (!suggestion) return

    e.preventDefault()
    // Cmd/Ctrl + event = force submit; Alt/Opt + event = force set without submitting
    const shouldSubmit =
      e.metaKey || e.ctrlKey ? true : e.altKey ? false : submit

    chatInputRef.current?.setInputValue(suggestion, {
      submit: shouldSubmit,
      focus: !shouldSubmit,
    })
  }

  function onSuggestionClick(e: React.MouseEvent<HTMLElement>): void {
    handleSuggestionEvent(e)
  }

  function onMessagesClick(e: React.MouseEvent<HTMLElement>): void {
    onContainerClick(e)
    onSuggestionClick(e)
  }

  function onSuggestionKeydown(e: React.KeyboardEvent<HTMLElement>): void {
    const isEnterOrSpace = e.key === "Enter" || e.key === " "
    if (!isEnterOrSpace) return
    handleSuggestionEvent(e)
  }

  const handleDialogProceed = useCallback(() => {
    const url = pendingUrlRef.current
    if (url) window.open(url, "_blank", "noopener,noreferrer")
    setPendingUrl(null)
  }, [])

  const handleDialogAlways = useCallback(() => {
    window.shinychat_always_open_external_links = true
    handleDialogProceed()
  }, [handleDialogProceed])

  const handleDialogCancel = useCallback(() => {
    setPendingUrl(null)
  }, [])

  const onSend = useCallback(() => {
    scrollToBottom()
  }, [scrollToBottom])

  return (
    <>
      <div className="shiny-chat-messages-wrapper">
        <div className="shiny-chat-messages" ref={scrollRef}>
          <div
            className="shiny-chat-messages-content"
            ref={contentRef}
            role="log"
            aria-live="polite"
            onClick={onMessagesClick}
            onKeyDown={onSuggestionKeydown}
          >
            <ChatMessages messages={messages} iconAssistant={iconAssistant} />
            {streamingMessage && (
              <MessageErrorBoundary key={streamingMessage.id}>
                <ChatMessage
                  message={streamingMessage}
                  iconAssistant={iconAssistant}
                />
              </MessageErrorBoundary>
            )}
          </div>
        </div>
        <ScrollToBottomButton
          isAtBottom={isAtBottom}
          scrollToBottom={scrollToBottom}
          streaming={!!streamingMessage}
        />
      </div>

      <div
        className={
          inputDisabled ? "shiny-chat-input disabled" : "shiny-chat-input"
        }
        onClick={onContainerClick}
      >
        <ChatInput
          ref={chatInputRef}
          transport={transport}
          inputId={inputId}
          disabled={inputDisabled}
          hasTopShadow={!isAtBottom}
          placeholder={inputPlaceholder}
          onSend={onSend}
        />
      </div>

      {pendingUrl &&
        createPortal(
          <ExternalLinkDialogComponent
            url={pendingUrl}
            onProceed={handleDialogProceed}
            onAlways={handleDialogAlways}
            onCancel={handleDialogCancel}
          />,
          document.body,
        )}
    </>
  )
})
