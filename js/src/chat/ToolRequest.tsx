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
}

/** Ports ShinyToolRequest from the Lit implementation. */
export const ToolRequest = memo(function ToolRequest({
  toolName,
  toolTitle,
  intent,
  arguments: toolArguments,
}: ToolRequestProps) {
  return (
    <ToolCard
      toolName={toolName}
      toolTitle={toolTitle}
      intent={intent}
      icon={spinnerIcon}
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
