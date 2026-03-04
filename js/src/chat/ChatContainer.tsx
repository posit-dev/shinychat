import { useRef, useEffect, useCallback } from "react"
import { ChatMessages } from "./ChatMessages"
import { ChatInput, type ChatInputHandle } from "./ChatInput"
import { showExternalLinkConfirmation } from "./ExternalLinkDialog"
import { useChatState } from "./context"

// Declare custom elements used in JSX so TypeScript doesn't complain
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
  iconAssistant?: string
  inputId: string
}

export function ChatContainer({ iconAssistant, inputId }: ChatContainerProps) {
  const { inputDisabled, inputValue, inputPlaceholder } = useChatState()

  const chatInputRef = useRef<ChatInputHandle>(null)
  const sentinelRef = useRef<HTMLDivElement>(null)
  const inputAreaRef = useRef<HTMLDivElement>(null)

  // IntersectionObserver: add/remove shadow class on textarea when sentinel scrolls off-screen
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

  // External link click handler (intercepts [data-external-link] elements)
  const onContainerClick = useCallback((e: React.MouseEvent<HTMLElement>) => {
    const target = e.target as HTMLElement
    const linkEl = target.closest("a[data-external-link]") as HTMLAnchorElement | null
    if (!linkEl || !linkEl.href) return

    e.preventDefault()

    showExternalLinkConfirmation(linkEl.href)
      .then((confirmed) => {
        if (confirmed) {
          window.open(linkEl.href, "_blank", "noopener,noreferrer")
        }
      })
      .catch(() => {
        window.open(linkEl.href, "_blank", "noopener,noreferrer")
      })
  }, [])

  // Helper: extract suggestion text and submit flag from a clicked/keydown element
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

  const onSuggestionClick = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      handleSuggestionEvent(e)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  const onSuggestionKeydown = useCallback(
    (e: React.KeyboardEvent<HTMLElement>) => {
      const isEnterOrSpace = e.key === "Enter" || e.key === " "
      if (!isEnterOrSpace) return
      handleSuggestionEvent(e)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  )

  return (
    // Messages area (scrollable, grid row 1)
    <>
      <shiny-chat-messages
        onClick={onSuggestionClick}
        onKeyDown={onSuggestionKeydown}
      >
        <ChatMessages iconAssistant={iconAssistant} />
      </shiny-chat-messages>

      {/* Input area (sticky, grid row 2) */}
      <shiny-chat-input
        ref={inputAreaRef}
        onClick={onContainerClick}
      >
        <ChatInput
          ref={chatInputRef}
          inputId={inputId}
          disabled={inputDisabled}
          placeholder={inputPlaceholder}
          value={inputValue}
        />
      </shiny-chat-input>

      {/* Sentinel for IntersectionObserver — sits just below the input */}
      <div ref={sentinelRef} style={{ width: "100%", height: 0 }} />
    </>
  )
}
