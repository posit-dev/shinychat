import { memo, useRef, useEffect, useCallback } from "react"
import type { ChatMessageData } from "./state"
import { ShinyBoundMarkdown } from "../markdown/ShinyBoundMarkdown"
import { robot, dots_fade } from "../utils/icons"
import { chatTagToComponentMap } from "./chatTagToComponentMap"

interface ChatMessageProps {
  message: ChatMessageData
  iconAssistant?: string
}

export const ChatMessage = memo(function ChatMessage({
  message,
  iconAssistant,
}: ChatMessageProps) {
  const contentRef = useRef<HTMLDivElement>(null)

  const isUser = message.role === "user"
  const isEmpty = message.content.trim() === ""

  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    iconHtml = isEmpty ? dots_fade : (message.icon ?? iconAssistant ?? robot)
  }

  // Matches Lit implementation's behavior of making suggestion elements focusable
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

  // Re-run on content changes so suggestions added mid-stream are picked up
  useEffect(() => {
    makeSuggestionsAccessible()
  }, [message.content, makeSuggestionsAccessible])

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
        <ShinyBoundMarkdown
          content={message.content}
          contentType={message.contentType}
          streaming={message.streaming}
          onStreamEnd={makeSuggestionsAccessible}
          tagToComponentMap={chatTagToComponentMap}
        />
      </div>
    </div>
  )
})
