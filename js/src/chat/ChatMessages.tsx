import { memo, useState } from "react"
import { ChatMessage } from "./ChatMessage"
import { MessageErrorBoundary } from "./MessageErrorBoundary"
import type { ChatMessageData } from "./state"
import type { SubmitKey } from "./tiptap/submitShortcut"
import type { AttachmentPayload } from "./attachments"

export interface ChatMessagesProps {
  messages: ChatMessageData[]
  iconAssistant?: string
  onEdit?: (
    index: number,
    content: string,
    attachments: AttachmentPayload[],
  ) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  disabled?: boolean
  inputId: string
  submitKey?: SubmitKey
  uploadAccept?: string[]
  maxUploadSize?: number | null
  enableUpload?: boolean
}

export const ChatMessages = memo(function ChatMessages({
  messages,
  iconAssistant,
  onEdit,
  onNavigate,
  disabled,
  inputId,
  submitKey,
  uploadAccept,
  maxUploadSize,
  enableUpload,
}: ChatMessagesProps) {
  // Only one message can be edited at a time: opening edit on any message
  // overwrites this index, which implicitly closes whichever one was open.
  const [editingIndex, setEditingIndex] = useState<number | null>(null)

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
            inputId={inputId}
            submitKey={submitKey}
            uploadAccept={uploadAccept}
            maxUploadSize={maxUploadSize}
            enableUpload={enableUpload}
            isEditing={i === editingIndex}
            onStartEdit={() => setEditingIndex(i)}
            onCancelEdit={() => setEditingIndex(null)}
          />
        </MessageErrorBoundary>
      ))}
    </>
  )
})
