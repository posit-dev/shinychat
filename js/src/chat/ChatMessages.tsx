import { ChatMessage } from "./ChatMessage"
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
        <ChatMessage key={msg.id} message={msg} iconAssistant={iconAssistant} />
      ))}
    </>
  )
}
