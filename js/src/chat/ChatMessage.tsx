import { memo } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
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
  const hasContent =
    message.content.trim() !== "" ||
    message.blocks.some((b) => b.type === "thinking")

  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    iconHtml = hasContent ? (message.icon ?? iconAssistant ?? robot) : dots_fade
  }

  const roleClass = isUser ? "shiny-chat-user-message" : "shiny-chat-message"

  return (
    <div className={roleClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
        {message.blocks.map((block, i) => {
          if (block.type === "thinking") {
            return (
              <ThinkingDisplay
                key={i}
                thinking={block}
                messageId={`${message.id}-${i}`}
              />
            )
          }
          const isLast = i === message.blocks.length - 1
          const el = (
            <MarkdownContent
              key={i}
              content={block.content}
              contentType={block.contentType}
              role={message.role}
              streaming={message.streaming && isLast}
              tagToComponentMap={chatTagToComponentMap}
            />
          )
          if (block.contentType === "text") {
            return (
              <div key={i} className="content-type-text">
                {el}
              </div>
            )
          }
          return el
        })}
      </div>
    </div>
  )
})
