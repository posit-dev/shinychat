import { useRef, useEffect, useCallback } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { robot, dots_fade } from "../utils/icons"

interface ChatMessageProps {
  message: ChatMessageData
  iconAssistant?: string
}

export function ChatMessage({ message, iconAssistant }: ChatMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  const isUser = message.role === "user"
  const isEmpty = message.content.trim() === ""

  // Determine icon HTML to render:
  // - Assistant messages: show dots_fade spinner while empty, then robot (or
  //   custom) once content arrives
  // - User messages: show icon only if one is explicitly provided
  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    iconHtml = isEmpty ? dots_fade : (message.icon ?? iconAssistant ?? robot)
  }

  // Make suggestion elements keyboard-accessible. Only process elements that
  // don't already have tabindex set (matching Lit behavior).
  const makeSuggestionsAccessible = useCallback(() => {
    if (!contentRef.current) return
    const suggestions = contentRef.current.querySelectorAll(
      ".suggestion, [data-suggestion]",
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

  // Run after every render so suggestions added mid-stream are picked up.
  // The hasAttribute("tabindex") guard prevents redundant work.
  useEffect(() => {
    makeSuggestionsAccessible()
  })

  const roleClass = isUser ? "shiny-chat-user-message" : "shiny-chat-message"
  const contentTypeClass =
    message.contentType === "text" ? " content-type-text" : ""

  return (
    <div className={roleClass + contentTypeClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content" ref={contentRef}>
        <MarkdownContent
          content={message.content}
          contentType={message.contentType}
          streaming={message.streaming}
          onStreamEnd={makeSuggestionsAccessible}
        />
      </div>
    </div>
  )
}
