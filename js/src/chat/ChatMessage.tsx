import { memo, useMemo, useState, useRef, useCallback, useEffect } from "react"
import { BlockErrorBoundary } from "./BlockErrorBoundary"
import {
  deriveToolGroupIdentity,
  type ChatMessageData,
  type ContentBlock,
  type MessageBlock,
} from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { ToolGroup } from "./ToolGroup"
import { WebActivity } from "./WebActivity"
import { HtmlBlockContent } from "./HtmlBlockContent"
import { robot, dots_fade, arrowUpShort, pencil } from "../utils/icons"
import {
  chatTagToComponentMap,
  untrustedChatTagToComponentMap,
} from "./chatTagToComponentMap"
import { useSlashCommands, useToolGrouping, useChatToolState } from "./context"
import { CommandChip } from "./CommandChip"
import type { SlashCommandDef } from "../transport/types"
import type { ComponentType } from "react"
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
import { CitationCollectorProvider } from "./citationCollector"
import { SourcesSummary } from "./SourcesSummary"

type TagComponentMap = Record<string, ComponentType<unknown>>

interface TrustedContentBlock extends ContentBlock {
  trusted: true
  tagMap: TagComponentMap
}

interface UntrustedContentBlock extends ContentBlock {
  trusted: false
  tagMap: TagComponentMap | undefined
}

type ClassifiedContentBlock = TrustedContentBlock | UntrustedContentBlock

function classifyContentBlock(
  block: ContentBlock,
  isUser: boolean,
): ClassifiedContentBlock {
  if (isUser) {
    return { ...block, trusted: false, tagMap: undefined }
  }
  return block.contentType === "html"
    ? { ...block, trusted: true, tagMap: chatTagToComponentMap }
    : { ...block, trusted: false, tagMap: untrustedChatTagToComponentMap }
}

const TOUCH_HOLD_MS = 500
const TOUCH_MOVE_CANCEL_PX = 10
// Delay before the icon-off pending indicator appears, so a fast response
// never flashes it in.
const PENDING_INDICATOR_DELAY_MS = 500
// Crossfade duration between the pending indicator and the first content --
// matches the site-wide 0.2s micro-transition used elsewhere (thinking dot
// appear, thinking label crossfade, disclosure rotation).
const PENDING_INDICATOR_FADE_MS = 200

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
  siblingNavigationPending?: boolean
  disabled?: boolean
  inputId?: string
  submitKey?: SubmitKey
  isEditing?: boolean
  onStartEdit?: (id: string) => void
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
  siblingNavigationPending = false,
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
  const toolGrouping = useToolGrouping()
  const { supersededRequests } = useChatToolState()
  const [lightbox, setLightbox] = useState<{
    src: string
    name: string
    mime: string
  } | null>(null)
  const [hasEditText, setHasEditText] = useState(false)
  const editRef = useRef<TiptapInputHandle>(null)
  const isUser = message.role === "user"

  const blocks = message.blocks

  // Drop running requests whose result has rendered elsewhere in the transcript
  // (the router can only pair the two within one content string), then any group
  // left empty. Done here so `hasContent` reflects what is actually visible.
  // Original block indices are kept for stable React keys. A group that loses
  // a call rederives its whole identity (title, segments, icon, count) from the
  // survivors so the row describes what it renders.
  const visibleBlocks = useMemo(() => {
    const out: { block: MessageBlock; index: number }[] = []
    blocks.forEach((block, index) => {
      if (block.type !== "tool_loop") {
        out.push({ block, index })
        return
      }
      const groups = block.groups
        .map((g) => {
          const calls = g.calls.filter(
            (c) =>
              !(c.status === "running" && supersededRequests.has(c.requestId)),
          )
          return calls.length === g.calls.length
            ? g
            : { ...g, calls, ...deriveToolGroupIdentity(calls) }
        })
        .filter((g) => g.calls.length > 0)
      if (groups.length > 0) out.push({ block: { ...block, groups }, index })
    })
    return out
  }, [blocks, supersededRequests])

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
    visibleBlocks.some(
      ({ block }) =>
        block.type === "thinking" ||
        block.type === "tool_loop" ||
        block.type === "web_activity" ||
        block.type === "html_block",
    ) ||
    (message.attachments?.length ?? 0) > 0 ||
    message.cancelled

  const resolvedIcon = isUser ? undefined : (message.icon ?? iconAssistant)
  const [showPendingDots, setShowPendingDots] = useState(false)
  const [pendingExiting, setPendingExiting] = useState(false)
  const [contentEntering, setContentEntering] = useState(false)

  // Arm the delayed pending indicator while waiting for the first token.
  useEffect(() => {
    if (isUser || resolvedIcon !== "" || hasContent) return
    const timer = setTimeout(
      () => setShowPendingDots(true),
      PENDING_INDICATOR_DELAY_MS,
    )
    return () => clearTimeout(timer)
  }, [isUser, resolvedIcon, hasContent])

  // Once content arrives, crossfade the indicator out and the first content
  // in instead of swapping instantly. A response fast enough to beat the
  // delay above never showed the indicator, so there's nothing to fade from.
  useEffect(() => {
    if (!hasContent || !showPendingDots) return
    setPendingExiting(true)
    setContentEntering(true)
    const timer = setTimeout(() => {
      setShowPendingDots(false)
      setPendingExiting(false)
      setContentEntering(false)
    }, PENDING_INDICATOR_FADE_MS)
    return () => clearTimeout(timer)
  }, [hasContent, showPendingDots])

  let iconHtml: string | undefined
  const showInlinePendingDots =
    !isUser && resolvedIcon === "" && showPendingDots
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    // Resolve the assistant icon through the per-message -> container chain. An
    // explicit "" (from icon_assistant=False / icon=False) removes the icon
    // entirely: no glyph in the icon slot. The pending dots move inline into
    // the content area instead (see showPendingDots above), so waiting for a
    // response still reads as "in progress" rather than dead air.
    if (resolvedIcon === "") {
      iconHtml = undefined
    } else {
      iconHtml = hasContent ? (resolvedIcon ?? robot) : dots_fade
    }
  }

  // Nothing left to render — e.g. a request-only message whose result rendered
  // in another message and superseded it. Emit no row at all; an icon or the
  // streaming dots would read as a stray empty turn. The pending-response
  // placeholder and in-flight streams are legitimately empty, so they stay.
  if (!hasContent && !message.streaming && !message.isPlaceholder) return null

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

  // Each block renders inside its own error boundary so a block that throws
  // (e.g. malformed server-provided tool metadata) degrades to an inline
  // notice instead of taking the whole message down with it.
  const renderMessageBlock = (
    block: MessageBlock,
    i: number,
  ): React.ReactNode => {
    if (block.type === "thinking") {
      return (
        <ThinkingDisplay
          key={i}
          thinking={block}
          messageId={`${message.id}-${i}`}
        />
      )
    }
    const isLast = i === blocks.length - 1

    if (block.type === "tool_loop") {
      return (
        <div key={i} className="shiny-chat-tool-loop">
          {block.groups.map((group) => (
            <ToolGroup key={group.key} group={group} />
          ))}
        </div>
      )
    }

    // A structured web activity renders directly — no markdown-pipeline
    // round-trip.
    if (block.type === "web_activity") {
      return <WebActivity key={i} items={block.items} />
    }

    // A structured raw-HTML island: server-authored trusted HTML rendered
    // directly through the shared RawHTML sink.
    if (block.type === "html_block") {
      return (
        <HtmlBlockContent
          key={i}
          content={block.content}
          htmlDeps={block.htmlDeps}
        />
      )
    }

    if (block.type !== "content") return null
    const cb = classifyContentBlock(block, isUser)

    if (leadingCommand && i === 0) {
      const chip = <CommandChip name={leadingCommand.commandName} />
      const content = leadingCommand.remainingText || ""

      if (cb.contentType === "text") {
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
          contentType={cb.contentType}
          role={message.role}
          streaming={message.streaming && isLast}
          tagToComponentMap={cb.tagMap}
          prefix={chip}
        />
      )
    }

    const el = (
      <MarkdownContent
        key={i}
        content={cb.content}
        contentType={cb.contentType}
        role={message.role}
        streaming={message.streaming && isLast}
        tagToComponentMap={cb.tagMap}
      />
    )
    if (cb.contentType === "text") {
      return (
        <div key={i} className="content-type-text">
          {el}
        </div>
      )
    }
    return el
  }

  const messageBlocks = visibleBlocks.map(({ block, index: i }) => (
    <BlockErrorBoundary
      key={i}
      context={`${block.type} block`}
      // Block object identity: the reducer preserves references for blocks an
      // update didn't touch, so a contained error retries exactly when the
      // failing block's data changes.
      resetKey={block}
      fallback={
        // Markdown rendering failing doesn't make the text itself useless.
        block.type === "content" ? (
          <div className="shiny-chat-block-error" role="alert">
            <pre>{block.content}</pre>
          </div>
        ) : undefined
      }
    >
      {renderMessageBlock(block, i)}
    </BlockErrorBoundary>
  ))

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
      <div
        className="shiny-chat-message-content"
        data-pending={showInlinePendingDots || undefined}
      >
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
                dangerouslySetInnerHTML={{ __html: arrowUpShort }}
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
            {showInlinePendingDots && (
              <div
                className="shiny-chat-pending-indicator"
                data-exiting={pendingExiting || undefined}
                aria-hidden="true"
                dangerouslySetInnerHTML={{ __html: dots_fade }}
              />
            )}
            {/* User attachments sit above their text (mirroring the input tray);
                assistant attachments come after the prose that introduces them. */}
            {isUser && attachmentsEl}
            <div
              className="shiny-chat-message-body"
              data-entering={contentEntering || undefined}
            >
              <CitationCollectorProvider>
                {messageBlocks}
                {!isUser && <SourcesSummary />}
              </CitationCollectorProvider>
            </div>
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
                  disabled={
                    message.siblings.index === 0 ||
                    disabled ||
                    siblingNavigationPending
                  }
                  onClick={() => onNavigate?.(index, "prev")}
                  aria-label="Previous version"
                >
                  ‹
                </button>
                <span aria-live="polite">
                  {message.siblings.index + 1} / {message.siblings.total}
                </span>
                <button
                  type="button"
                  disabled={
                    message.siblings.index === message.siblings.total - 1 ||
                    disabled ||
                    siblingNavigationPending
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
                  onStartEdit?.(message.id)
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
