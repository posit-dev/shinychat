import { useChatState } from "./context"
import { ChatMessage } from "./ChatMessage"

export function ChatMessages({ iconAssistant }: { iconAssistant?: string }) {
  const { messages } = useChatState()

  return (
    <>
      {messages.map((msg) => (
        <ChatMessage
          key={msg.id}
          message={msg}
          iconAssistant={iconAssistant}
        />
      ))}
    </>
  )
}
