import { ToolCard } from "./ToolCard"
import { useChatState } from "./context"
import { MarkdownContent } from "../markdown/MarkdownContent"

export interface ToolRequestProps {
  requestId: string
  toolName: string
  toolTitle?: string
  intent?: string
  arguments: string
}

/**
 * Formats a string as a Markdown code block with the specified language.
 */
function markdownCodeBlock(content: string, language: string = "markdown"): string {
  const backticks = "`".repeat(8)
  return `${backticks}${language}\n${content}\n${backticks}`
}

/**
 * Displays information about a pending tool request.
 * Hidden when `requestId` is in `state.hiddenToolRequests`.
 * Ports `ShinyToolRequest` from the Lit implementation.
 */
export function ToolRequest({
  requestId,
  toolName,
  toolTitle,
  intent,
  arguments: toolArguments,
}: ToolRequestProps) {
  const state = useChatState()

  if (state.hiddenToolRequests.has(requestId)) {
    return null
  }

  const spinnerIcon = '<div class="spinner-border" role="status"></div>'

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
}
