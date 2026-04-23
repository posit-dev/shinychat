import { memo } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
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
  const isUser = message.role === "user"
  const isEmpty = message.content.trim() === ""

  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    iconHtml = isEmpty ? dots_fade : (message.icon ?? iconAssistant ?? robot)
  }

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
      <div className="shiny-chat-message-content">
        {(
          message.segments ?? [
            { content: message.content, contentType: message.contentType },
          ]
        ).map((seg, i, arr) => (
          <MarkdownContent
            key={i}
            content={seg.content}
            contentType={seg.contentType}
            role={message.role}
            streaming={message.streaming && i === arr.length - 1}
            tagToComponentMap={chatTagToComponentMap}
          />
        ))}
      </div>
    </div>
  )
})
