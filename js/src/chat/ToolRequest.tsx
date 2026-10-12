import { memo } from "react"
import { ToolCard } from "./ToolCard"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"

const spinnerIcon =
  '<div class="spinner-border" role="status"><span class="visually-hidden">Running…</span></div>'

export interface ToolRequestProps {
  toolName: string
  toolTitle?: string
  intent?: string
  arguments: string
  /** Open the card body on mount (used under a Tier-2 row, which hides the
   * card's own header and so its toggle). */
  expanded?: boolean
}

/** Ports ShinyToolRequest from the Lit implementation. */
export const ToolRequest = memo(function ToolRequest({
  toolName,
  toolTitle,
  intent,
  arguments: toolArguments,
  expanded,
}: ToolRequestProps) {
  return (
    <ToolCard
      toolName={toolName}
      toolTitle={toolTitle}
      intent={intent}
      icon={spinnerIcon}
      resetKey={toolArguments}
      initialExpanded={expanded}
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
