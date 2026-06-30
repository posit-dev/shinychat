import { memo } from "react"
import { ChatMessage } from "./ChatMessage"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import type { ChatMessageData } from "./state"

export const ChatMessages = memo(function ChatMessages({
  messages,
  iconAssistant,
  onEdit,
  onNavigate,
  disabled,
}: {
  messages: ChatMessageData[]
  iconAssistant?: string
  onEdit?: (index: number, content: string) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  disabled?: boolean
}) {
  return (
    <>
      {messages.map((msg, i) => (
        <MessageErrorBoundary key={msg.id}>
          <ChatMessage
            message={msg}
            index={i}
            iconAssistant={iconAssistant}
            onEdit={onEdit}
            onNavigate={onNavigate}
            disabled={disabled}
          />
        </MessageErrorBoundary>
      ))}
    </>
  )
})
