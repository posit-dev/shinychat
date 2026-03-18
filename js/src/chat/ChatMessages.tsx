import { ChatMessage } from "./ChatMessage"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import type { ChatMessageData } from "./state"

export function ChatMessages({
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
          <ChatMessage message={msg} iconAssistant={iconAssistant} />
        </MessageErrorBoundary>
      ))}
    </>
  )
}
