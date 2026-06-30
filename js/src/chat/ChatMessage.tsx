import { memo, useState, useRef } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { robot, dots_fade, xLg, arrowUpCircleFill } from "../utils/icons"
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

const pencilIcon = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M12.146.146a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1 0 .708l-10 10a.5.5 0 0 1-.168.11l-5 2a.5.5 0 0 1-.65-.65l2-5a.5.5 0 0 1 .11-.168zM11.207 2.5 13.5 4.793 14.793 3.5 12.5 1.207zm1.586 3L10.5 3.207 4 9.707V10h.5a.5.5 0 0 1 .5.5v.5h.5a.5.5 0 0 1 .5.5v.5h.293zm-9.761 5.175-.106.106-1.528 3.821 3.821-1.528.106-.106A.5.5 0 0 1 5 12.5V12h-.5a.5.5 0 0 1-.5-.5V11h-.5a.5.5 0 0 1-.468-.325z"/></svg>`

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
  index: number
  iconAssistant?: string
  onEdit?: (index: number, content: string) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  disabled?: boolean
}

export const ChatMessage = memo(function ChatMessage({
  message,
  index,
  iconAssistant,
  onEdit,
  onNavigate,
  disabled,
}: ChatMessageProps) {
  const slashCommands = useSlashCommands()
  const [lightbox, setLightbox] = useState<{
    src: string
    name: string
    mime: string
  } | null>(null)
  const [editing, setEditing] = useState(false)
  const [editText, setEditText] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)
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

  const messageBlocks = message.blocks.map((block, i) => {
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
  })

  const lightboxPortal = lightbox && (
    <AttachmentLightbox
      src={lightbox.src}
      name={lightbox.name}
      mime={lightbox.mime}
      onClose={() => setLightbox(null)}
    />
  )

  return (
    <div className={roleClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
        {editing ? (
          <div className="shiny-chat-edit-form">
            <textarea
              ref={textareaRef}
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  onEdit?.(index, editText)
                  setEditing(false)
                } else if (e.key === "Escape") {
                  e.preventDefault()
                  setEditing(false)
                }
              }}
              onFocus={() => textareaRef.current?.select()}
              autoFocus
            />
            <div className="shiny-chat-edit-actions">
              <button
                type="button"
                className="shiny-chat-edit-cancel"
                onClick={() => setEditing(false)}
                aria-label="Cancel edit"
                title="Cancel"
                dangerouslySetInnerHTML={{ __html: xLg }}
              />
              <button
                type="button"
                className="shiny-chat-edit-submit"
                onClick={() => {
                  onEdit?.(index, editText)
                  setEditing(false)
                }}
                aria-label="Save and resend"
                title="Save and resend"
                dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
              />
            </div>
          </div>
        ) : (
          <>
            {/* User attachments sit above their text (mirroring the input tray);
                assistant attachments come after the prose that introduces them. */}
            {isUser && attachmentsEl}
            {messageBlocks}
            {!isUser && attachmentsEl}
            {message.cancelled && (
              <div className="shiny-chat-message-cancelled">
                Response cancelled
              </div>
            )}
          </>
        )}
      </div>
      {isUser &&
        !editing &&
        ((onEdit && !disabled) ||
          (message.siblings && message.siblings.total > 1)) && (
          <div className="shiny-chat-message-footer">
            {message.siblings && message.siblings.total > 1 && (
              <div className="shiny-chat-sibling-nav">
                <button
                  type="button"
                  disabled={message.siblings.index === 0 || disabled}
                  onClick={() => onNavigate?.(index, "prev")}
                  aria-label="Previous version"
                >
                  ‹
                </button>
                <span>
                  {message.siblings.index + 1} / {message.siblings.total}
                </span>
                <button
                  type="button"
                  disabled={
                    message.siblings.index === message.siblings.total - 1 ||
                    disabled
                  }
                  onClick={() => onNavigate?.(index, "next")}
                  aria-label="Next version"
                >
                  ›
                </button>
              </div>
            )}
            {onEdit && !disabled && (
              <button
                type="button"
                className="shiny-chat-edit-btn"
                onClick={() => {
                  setEditText(message.content)
                  setEditing(true)
                }}
                aria-label="Edit message"
                title="Edit message"
                dangerouslySetInnerHTML={{ __html: pencilIcon }}
              />
            )}
          </div>
        )}
      {lightboxPortal}
    </div>
  )
})
