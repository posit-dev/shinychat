import {
  useState,
  useRef,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react"
import { createPortal } from "react-dom"
import { ChatMessages } from "./ChatMessages"
import { ChatInput, type ChatInputHandle } from "./ChatInput"
import { ExternalLinkDialogComponent } from "./ExternalLinkDialog"
import { useAutoScroll } from "../markdown/useAutoScroll"
import type { ChatMessageData } from "./state"
import type { ChatTransport } from "../transport/types"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "shiny-chat-messages": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement>,
        HTMLElement
      >
      "shiny-chat-input": React.DetailedHTMLProps<
        React.HTMLAttributes<HTMLElement> & { ref?: React.Ref<HTMLElement> },
        HTMLElement
      >
    }
  }
}

export interface ChatContainerProps {
  transport: ChatTransport
  messages: ChatMessageData[]
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
    inputDisabled,
    inputPlaceholder,
    iconAssistant,
    inputId,
  },
  ref,
) {
  const chatInputRef = useRef<ChatInputHandle>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const inputAreaRef = useRef<HTMLDivElement>(null)

  const [pendingUrl, setPendingUrl] = useState<string | null>(null)
  const pendingUrlRef = useRef<string | null>(null)
  pendingUrlRef.current = pendingUrl

  const isStreaming = messages[messages.length - 1]?.streaming ?? false
  const { containerRef: messagesRef, engageStickToBottom } = useAutoScroll({
    streaming: isStreaming,
    contentDependency: messages,
    scrollOnContentChange: true,
  })

  useImperativeHandle(ref, () => ({
    setInputValue(...args) {
      chatInputRef.current?.setInputValue(...args)
    },
    focus() {
      chatInputRef.current?.focus()
    },
  }))

  useEffect(() => {
    const sentinel = sentinelRef.current
    const inputArea = inputAreaRef.current
    if (!sentinel || !inputArea) return

    const observer = new IntersectionObserver(
      (entries) => {
        const textarea = inputArea.querySelector("textarea")
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

  return (
    <>
      <shiny-chat-messages
        ref={messagesRef}
        role="log"
        aria-live="polite"
        onClick={onMessagesClick}
        onKeyDown={onSuggestionKeydown}
      >
        <ChatMessages messages={messages} iconAssistant={iconAssistant} />
      </shiny-chat-messages>

      <shiny-chat-input ref={inputAreaRef} onClick={onContainerClick}>
        <ChatInput
          ref={chatInputRef}
          transport={transport}
          inputId={inputId}
          disabled={inputDisabled}
          placeholder={inputPlaceholder}
          onSend={engageStickToBottom}
        />
      </shiny-chat-input>

      {/* IntersectionObserver sentinel: triggers shadow on the textarea
          when messages scroll behind the input area */}
      <div ref={sentinelRef} style={{ width: "100%", height: 0 }} />

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
