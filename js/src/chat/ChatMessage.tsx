import { memo, useState } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { robot, dots_fade } from "../utils/icons"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { useSlashCommands } from "./context"
import { CommandChip } from "./CommandChip"
import type { SlashCommandDef } from "../transport/types"
import {
  attachmentBadgeLabel,
  attachmentFamily,
  dataUrlByteSize,
} from "./attachments"
import { TextAttachmentPreview } from "./TextAttachmentPreview"
import { AttachmentLightbox } from "./AttachmentLightbox"

function parseLeadingCommand(
  content: string,
  commands: SlashCommandDef[],
): { commandName: string; remainingText: string } | null {
  if (!content.startsWith("/")) return null
  const withoutSlash = content.slice(1)
  const spaceIndex = withoutSlash.indexOf(" ")
  const commandName =
    spaceIndex === -1 ? withoutSlash : withoutSlash.slice(0, spaceIndex)
  const remainingText =
    spaceIndex === -1 ? "" : withoutSlash.slice(spaceIndex + 1).trim()
  const matched = commands.find((cmd) => cmd.name === commandName)
  if (!matched) return null
  return { commandName, remainingText }
}

interface ChatMessageProps {
  message: ChatMessageData
  iconAssistant?: string
}

export const ChatMessage = memo(function ChatMessage({
  message,
  iconAssistant,
}: ChatMessageProps) {
  const slashCommands = useSlashCommands()
  const [lightbox, setLightbox] = useState<{
    src: string
    name: string
    mime: string
  } | null>(null)
  const isUser = message.role === "user"
  const hasContent =
    message.content.trim() !== "" ||
    message.blocks.some((b) => b.type === "thinking") ||
    (message.attachments?.length ?? 0) > 0 ||
    message.cancelled

  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    iconHtml = hasContent ? (message.icon ?? iconAssistant ?? robot) : dots_fade
  }

  const leadingCommand = isUser
    ? parseLeadingCommand(message.content, slashCommands)
    : null
  const roleClass = isUser ? "shiny-chat-user-message" : "shiny-chat-message"

  const attachmentsEl =
    message.attachments && message.attachments.length > 0 ? (
      <div className="shiny-chat-message-attachments">
        {message.attachments.map((a, i) => {
          if (a.mime.startsWith("image/")) {
            const alt = a.name
              ? `Attached image: ${a.name}`
              : `Attached image ${i + 1}`
            return (
              <button
                key={i}
                type="button"
                className="shiny-chat-message-image-btn"
                title={a.name || undefined}
                aria-label={
                  a.name ? `View ${a.name}` : `View attached image ${i + 1}`
                }
                onClick={() =>
                  setLightbox({ src: a.data_url, name: a.name, mime: a.mime })
                }
              >
                <img
                  className="shiny-chat-message-image"
                  src={a.data_url}
                  alt={alt}
                />
              </button>
            )
          }
          if (attachmentFamily(a.mime) === "text") {
            return (
              <TextAttachmentPreview
                key={i}
                dataUrl={a.data_url}
                name={a.name}
                size={dataUrlByteSize(a.data_url)}
                onActivate={() =>
                  setLightbox({ src: a.data_url, name: a.name, mime: a.mime })
                }
              />
            )
          }
          return (
            <button
              key={i}
              type="button"
              className="shiny-chat-message-attachment-chip"
              title={a.name || undefined}
              aria-label={`View ${a.name || "attachment"}`}
              onClick={() =>
                setLightbox({ src: a.data_url, name: a.name, mime: a.mime })
              }
            >
              <span className="shiny-chat-attachment-badge">
                {attachmentBadgeLabel(a.name, a.mime)}
              </span>
              <span className="shiny-chat-attachment-name">
                {a.name || "attachment"}
              </span>
            </button>
          )
        })}
      </div>
    ) : null

  return (
    <div className={roleClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
        {/* User attachments sit above their text (mirroring the input tray);
            assistant attachments come after the prose that introduces them. */}
        {isUser && attachmentsEl}
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

          if (leadingCommand && i === 0) {
            const chip = <CommandChip name={leadingCommand.commandName} />
            const content = leadingCommand.remainingText || ""

            if (block.contentType === "text") {
              return (
                <div key={i} className="content-type-text">
                  {chip}
                  {content && ` ${content}`}
                </div>
              )
            }
            if (!content) {
              return <p key={i}>{chip}</p>
            }
            return (
              <MarkdownContent
                key={i}
                content={content}
                contentType={block.contentType}
                role={message.role}
                streaming={message.streaming && isLast}
                tagToComponentMap={chatTagToComponentMap}
                prefix={chip}
              />
            )
          }

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
        {!isUser && attachmentsEl}
        {message.cancelled && (
          <div className="shiny-chat-message-cancelled">Response cancelled</div>
        )}
      </div>
      {lightbox && (
        <AttachmentLightbox
          src={lightbox.src}
          name={lightbox.name}
          mime={lightbox.mime}
          onClose={() => setLightbox(null)}
        />
      )}
    </div>
  )
})
