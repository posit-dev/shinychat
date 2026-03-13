import { memo } from "react"
import { ToolCard } from "./ToolCard"
import { useChatToolState } from "./context"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"

const spinnerIcon = '<div class="spinner-border" role="status"></div>'

export interface ToolRequestProps {
  requestId: string
  toolName: string
  toolTitle?: string
  intent?: string
  arguments: string
}

/**
 * Displays information about a pending tool request.
 * Hidden when `requestId` is in `state.hiddenToolRequests`.
 * Ports `ShinyToolRequest` from the Lit implementation.
 */
export const ToolRequest = memo(function ToolRequest({
  requestId,
  toolName,
  toolTitle,
  intent,
  arguments: toolArguments,
}: ToolRequestProps) {
  const { hiddenToolRequests } = useChatToolState()

  if (hiddenToolRequests.has(requestId)) {
    return null
  }

  return (
    <ToolCard
      requestId={requestId}
      toolName={toolName}
      toolTitle={toolTitle}
      intent={intent}
      icon={spinnerIcon}
      titleTemplate="Running {title}"
    >
      <div className="shiny-tool-request__arguments">
        <strong>Tool arguments</strong>
        <MarkdownContent
          content={markdownCodeBlock(toolArguments, "json")}
          contentType="markdown"
          streaming={false}
        />
      </div>
    </ToolCard>
  )
})
