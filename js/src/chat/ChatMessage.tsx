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

  const segments = message.segments ?? [
    { content: message.content, contentType: message.contentType },
  ]

  return (
    <div className={roleClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
        {segments.map((seg, i, arr) => {
          const el = (
            <MarkdownContent
              key={i}
              content={seg.content}
              contentType={seg.contentType}
              role={message.role}
              streaming={message.streaming && i === arr.length - 1}
              tagToComponentMap={chatTagToComponentMap}
            />
          )
          if (seg.contentType === "text") {
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
