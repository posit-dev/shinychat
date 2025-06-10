import { JSX } from "preact/jsx-runtime"
import { ChatMessage } from "./ChatMessage"
import { ChatUserMessage } from "./ChatUserMessage"
import type { Message } from "./types"

export interface ChatMessagesProps {
  messages: Message[]
  iconAssistant?: string
}

export function ChatMessages({
  messages,
  iconAssistant,
}: ChatMessagesProps): JSX.Element {
  return (
    <div className="chat-messages">
      {messages.map((message, index) => {
        const key = message.id || `${message.role}-${index}`

        if (message.role === "user") {
          return <ChatUserMessage key={key} content={message.content} />
        } else {
          return (
            <ChatMessage
              key={key}
              content={message.content}
              contentType={message.content_type}
              streaming={
                message.chunk_type === "message_start" ||
                message.chunk_type === null
              }
              icon={message.icon || iconAssistant}
            />
          )
        }
      })}
    </div>
  )
}
