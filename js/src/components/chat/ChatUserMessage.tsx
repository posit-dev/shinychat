import { JSX } from "preact/jsx-runtime"
import { MarkdownStream } from "../MarkdownStream"

export interface ChatUserMessageProps {
  content: string
}

export function ChatUserMessage({
  content,
}: ChatUserMessageProps): JSX.Element {
  return (
    <div className="chat-user-message">
      <MarkdownStream content={content} contentType="semi-markdown" />
    </div>
  )
}
