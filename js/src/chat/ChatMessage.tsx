import { memo, useMemo, useState } from "react"
import {
  routeToolBlocks,
  type ChatMessageData,
  type MessageBlock,
} from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { ToolGroup } from "./ToolGroup"
import { robot, dots_fade } from "../utils/icons"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { useSlashCommands, useToolGrouping, useChatToolState } from "./context"
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
  const toolGrouping = useToolGrouping()
  const { hiddenToolRequests } = useChatToolState()
  const [lightbox, setLightbox] = useState<{
    src: string
    name: string
    mime: string
  } | null>(null)
  const isUser = message.role === "user"

  // Finalized messages already carry routed tool_loop blocks (built in the
  // reducer). While streaming, tool elements still live in content blocks, so
  // route them at render time — with the same grouping — so tool calls show
  // the Tier UI live and don't pop into it on finalize. An incomplete trailing
  // tool element stays as prose (the router leaves it) until it closes, and so
  // does everything after a code fence that has not been closed yet.
  const blocks = useMemo(
    () =>
      message.streaming
        ? routeToolBlocks(message.blocks, toolGrouping, true)
        : message.blocks,
    [message.streaming, message.blocks, toolGrouping],
  )

  // Drop running requests whose result has rendered elsewhere (hidden via
  // hide_tool_request), then any group left empty. Done here rather than in the
  // render pass so `hasContent` — and the decision to render a row at all —
  // reflect what is actually visible. The original block index is kept so React
  // keys stay stable when a block drops out.
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
              !(c.status === "running" && hiddenToolRequests.has(c.requestId)),
          )
          return calls.length === g.calls.length
            ? g
            : { ...g, calls, count: calls.length }
        })
        .filter((g) => g.calls.length > 0)
      if (groups.length > 0) out.push({ block: { ...block, groups }, index })
    })
    return out
  }, [blocks, hiddenToolRequests])

  const hasContent =
    message.content.trim() !== "" ||
    visibleBlocks.some(
      ({ block }) => block.type === "thinking" || block.type === "tool_loop",
    ) ||
    (message.attachments?.length ?? 0) > 0 ||
    message.cancelled

  let iconHtml: string | undefined
  if (isUser) {
    iconHtml = message.icon || undefined
  } else {
    // Resolve the assistant icon through the per-message -> container chain. An
    // explicit "" (from icon_assistant=False / icon=False) removes the icon
    // entirely: no glyph and no streaming dots in the icon slot.
    const resolved = message.icon ?? iconAssistant
    if (resolved === "") {
      iconHtml = undefined
    } else {
      iconHtml = hasContent ? (resolved ?? robot) : dots_fade
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
        {visibleBlocks.map(({ block, index: i }) => {
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
              <div key={i} className="shinychat-tool-loop">
                {block.groups.map((group) => (
                  <ToolGroup key={group.key} group={group} />
                ))}
              </div>
            )
          }

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
