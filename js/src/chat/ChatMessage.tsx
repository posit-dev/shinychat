import { memo } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { ThinkingDisplay } from "./ThinkingDisplay"
import { robot, dots_fade } from "../utils/icons"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { useSlashCommands } from "./context"
import { CommandChip } from "./CommandChip"
import type { SlashCommandDef } from "../transport/types"

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
  const isUser = message.role === "user"
  const hasContent =
    message.content.trim() !== "" ||
    message.blocks.some((b) => b.type === "thinking") ||
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

  return (
    <div className={roleClass}>
      {iconHtml && (
        <div
          className="message-icon"
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
      )}
      <div className="shiny-chat-message-content">
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
        {message.cancelled && (
          <div className="shiny-chat-message-cancelled">Response cancelled</div>
        )}
      </div>
    </div>
  )
})
