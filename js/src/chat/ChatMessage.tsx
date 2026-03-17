import { memo } from "react"
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
        <ShinyBoundMarkdown
          content={message.content}
          contentType={message.contentType}
          streaming={message.streaming}
          tagToComponentMap={chatTagToComponentMap}
        />
      </div>
    </div>
  )
})
