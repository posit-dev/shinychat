import { memo, useState, useRef, useCallback, useEffect } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { robot, dots_fade, arrowUpCircleFill, pencil } from "../utils/icons"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { useSlashCommands } from "./context"
import { CommandChip } from "./CommandChip"
import type { SlashCommandDef } from "../transport/types"
import {
  attachmentBadgeLabel,
  attachmentFamily,
  dataUrlByteSize,
  type AttachmentPayload,
} from "./attachments"
import { TextAttachmentPreview } from "./TextAttachmentPreview"
import { AttachmentLightbox } from "./AttachmentLightbox"
import { TiptapInput, type TiptapInputHandle } from "./TiptapInput"
import type { SubmitKey } from "./tiptap/submitShortcut"
import { useAttachmentStaging } from "./useAttachmentStaging"
import { AttachmentTray } from "./AttachmentTray"

const TOUCH_HOLD_MS = 500
const TOUCH_MOVE_CANCEL_PX = 10

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
  onEdit?: (
    index: number,
    content: string,
    attachments: AttachmentPayload[],
  ) => void
  onNavigate?: (index: number, direction: "prev" | "next") => void
  disabled?: boolean
  inputId?: string
  submitKey?: SubmitKey
  isEditing?: boolean
  onStartEdit?: () => void
  onCancelEdit?: () => void
  uploadAccept?: string[]
  maxUploadSize?: number | null
  enableUpload?: boolean
}

export const ChatMessage = memo(function ChatMessage({
  message,
  index,
  iconAssistant,
  onEdit,
  onNavigate,
  disabled,
  inputId,
  submitKey = "enter",
  isEditing = false,
  onStartEdit,
  onCancelEdit,
  uploadAccept = [],
  maxUploadSize = null,
  enableUpload,
}: ChatMessageProps) {
  const slashCommands = useSlashCommands()
  const [lightbox, setLightbox] = useState<{
    src: string
    name: string
    mime: string
  } | null>(null)
  const [hasEditText, setHasEditText] = useState(false)
  const editRef = useRef<TiptapInputHandle>(null)
  const isUser = message.role === "user"
  const touchHoldEnabled = isUser && !!onEdit && !disabled && !isEditing

  const [touchRevealed, setTouchRevealed] = useState(false)
  const touchHoldTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const touchHoldStartRef = useRef<{ x: number; y: number } | null>(null)
  const touchHoldRevealedRef = useRef(false)
  const rootRef = useRef<HTMLDivElement>(null)

  const focusEditor = useCallback(() => editRef.current?.focus(), [])
  const staging = useAttachmentStaging({
    uploadAccept,
    maxUploadSize,
    enableUpload,
    focusEditor,
  })
  const { applyPayloads, getPayloads, onPaste, onDrop } = staging

  // Seed the editor only on the transition into editing. Re-seeding when
  // message.content/attachments change while an edit is open would clobber the
  // user's in-progress text and steal focus, so guard on the previous state.
  const wasEditingRef = useRef(false)
  useEffect(() => {
    if (isEditing && !wasEditingRef.current) {
      editRef.current?.setInputValue(message.content, { focus: true })
      applyPayloads(message.attachments ?? [], "set")
    }
    wasEditingRef.current = isEditing
  }, [isEditing, message.content, message.attachments, applyPayloads])

  const handleSaveEdit = useCallback(
    (content: string): boolean => {
      if (disabled) return false
      onEdit?.(index, content, getPayloads())
      onCancelEdit?.()
      return true
    },
    [onEdit, onCancelEdit, index, disabled, getPayloads],
  )
  // Lets Enter submit an attachments-only edit even though the editor doc is
  // empty (TiptapInput blocks empty submits otherwise).
  const canSubmitEmpty = useCallback(
    () => getPayloads().length > 0,
    [getPayloads],
  )

  const clearTouchHoldTimer = useCallback(() => {
    if (touchHoldTimerRef.current !== null) {
      clearTimeout(touchHoldTimerRef.current)
      touchHoldTimerRef.current = null
    }
  }, [])

  const handleBubblePointerDown = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      if (e.pointerType !== "touch") return
      touchHoldStartRef.current = { x: e.clientX, y: e.clientY }
      touchHoldRevealedRef.current = false
      clearTouchHoldTimer()
      touchHoldTimerRef.current = setTimeout(() => {
        touchHoldTimerRef.current = null
        touchHoldRevealedRef.current = true
        setTouchRevealed(true)
      }, TOUCH_HOLD_MS)
    },
    [clearTouchHoldTimer],
  )

  const handleBubblePointerMove = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const start = touchHoldStartRef.current
      if (!start) return
      const moved = Math.hypot(e.clientX - start.x, e.clientY - start.y)
      if (moved > TOUCH_MOVE_CANCEL_PX) {
        touchHoldStartRef.current = null
        clearTouchHoldTimer()
      }
    },
    [clearTouchHoldTimer],
  )

  const handleBubblePointerUp = useCallback(
    (e: React.PointerEvent<HTMLDivElement>) => {
      const wasHolding = touchHoldStartRef.current !== null
      touchHoldStartRef.current = null
      clearTouchHoldTimer()
      // The hold just revealed the button; swallow the trailing click so it
      // doesn't also activate whatever else is under the finger.
      if (wasHolding && touchHoldRevealedRef.current) {
        e.preventDefault()
      }
    },
    [clearTouchHoldTimer],
  )

  const handleBubblePointerCancel = useCallback(() => {
    touchHoldStartRef.current = null
    clearTouchHoldTimer()
  }, [clearTouchHoldTimer])

  const handleBubbleContextMenu = useCallback((e: React.MouseEvent) => {
    // Suppress the native long-press context menu/selection callout during
    // (or just after) a touch hold; a deliberate tap-drag or double-tap can
    // still select text normally.
    if (touchHoldStartRef.current !== null || touchHoldRevealedRef.current) {
      e.preventDefault()
    }
  }, [])

  useEffect(() => {
    if (!touchRevealed) return
    const onPointerDownOutside = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setTouchRevealed(false)
      }
    }
    document.addEventListener("pointerdown", onPointerDownOutside, true)
    return () =>
      document.removeEventListener("pointerdown", onPointerDownOutside, true)
  }, [touchRevealed])

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
    <div
      ref={rootRef}
      className={roleClass}
      data-touch-revealed={touchRevealed || undefined}
      onPointerDown={touchHoldEnabled ? handleBubblePointerDown : undefined}
      onPointerMove={touchHoldEnabled ? handleBubblePointerMove : undefined}
      onPointerUp={touchHoldEnabled ? handleBubblePointerUp : undefined}
      onPointerCancel={touchHoldEnabled ? handleBubblePointerCancel : undefined}
      onContextMenu={touchHoldEnabled ? handleBubbleContextMenu : undefined}
    >
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
        {isEditing ? (
          <div
            className="shiny-chat-edit-wrap"
            onKeyDownCapture={(e) => {
              if (e.key === "Escape") {
                e.preventDefault()
                onCancelEdit?.()
              }
            }}
          >
            <div
              className="shiny-chat-edit-box"
              onDropCapture={onDrop}
              onDragOver={(e) => e.preventDefault()}
              onPasteCapture={onPaste}
            >
              <AttachmentTray
                staging={staging}
                uploadAccept={uploadAccept}
                maxUploadSize={maxUploadSize}
                enableUpload={enableUpload}
                disabled={disabled}
              />
              <TiptapInput
                ref={editRef}
                inputId={`${inputId}-edit`}
                placeholder="Edit message"
                slashCommands={[]}
                userMessages={[]}
                submitKey={submitKey}
                onHasTextChange={setHasEditText}
                onSubmit={handleSaveEdit}
                canSubmitEmpty={canSubmitEmpty}
              />
              <button
                type="button"
                className="shiny-chat-btn-send"
                disabled={
                  disabled || (!hasEditText && staging.attachments.length === 0)
                }
                onClick={() => {
                  const content = editRef.current?.serializeEditor() ?? ""
                  handleSaveEdit(content)
                }}
                aria-label="Save and resend"
                title="Save and resend"
                dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
              />
            </div>
            <button
              type="button"
              className="shiny-chat-edit-cancel-outside"
              onClick={() => onCancelEdit?.()}
            >
              Cancel
            </button>
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
        !isEditing &&
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
                  setTouchRevealed(false)
                  onStartEdit?.()
                }}
                aria-label="Edit message"
                title="Edit message"
                dangerouslySetInnerHTML={{ __html: pencil }}
              />
            )}
          </div>
        )}
      {lightboxPortal}
    </div>
  )
})
