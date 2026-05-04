import { memo } from "react"
import { ChatMessage } from "./ChatMessage"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import type { ChatMessageData } from "./state"

export const ChatMessages = memo(function ChatMessages({
  messages,
  iconAssistant,
}: {
  messages: ChatMessageData[]
  iconAssistant?: string
}) {
  return (
    <>
      {messages.map((msg) => (
        <MessageErrorBoundary key={msg.id}>
          {msg.role === "thinking" ? (
            <ThinkingDisplay message={msg} />
          ) : (
            <ChatMessage message={msg} iconAssistant={iconAssistant} />
          )}
        </MessageErrorBoundary>
      ))}
    </>
  )
})
