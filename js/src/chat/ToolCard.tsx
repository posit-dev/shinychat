import { useState, type ReactNode } from "react"
import { wrenchAdjustable, plus } from "../utils/icons"

export interface ToolCardProps {
  requestId: string
  toolName: string
  toolTitle?: string
  intent?: string
  icon?: string
  classStatus?: string
  titleTemplate?: string
  children?: ReactNode
}

/**
 * Formats the tool title for display in the card header. Uses the
 * `titleTemplate`, replacing `{title}` with the actual title/name of the tool.
 */
function formatTitle(
  toolName: string,
  toolTitle: string | undefined,
  titleTemplate: string,
): string {
  const displayName = toolTitle || `${toolName}()`
  const spanWrapped = `<span class="tool-title-name">${displayName}</span>`
  return titleTemplate.replace("{title}", spanWrapped)
}

/**
 * Reusable collapsible tool card component with Bootstrap styling.
 * Ports `ShinyToolCard` from the Lit implementation.
 */
export function ToolCard({
  requestId,
  toolName,
  toolTitle,
  intent,
  icon,
  classStatus = "",
  titleTemplate = "{title}",
  children,
}: ToolCardProps) {
  const [expanded, setExpanded] = useState(false)

  const headerId = `tool-header-${requestId}`
  const contentId = `tool-content-${requestId}`
  const iconHtml = icon || wrenchAdjustable
  const formattedTitle = formatTitle(toolName, toolTitle, titleTemplate)

  function handleClick(e: React.MouseEvent) {
    e.preventDefault()
    setExpanded((prev) => !prev)
  }

  return (
    <div className="shiny-tool-card card bslib-card html-fill-item html-fill-container m-0">
      <button
        className="card-header"
        id={headerId}
        onClick={handleClick}
        aria-expanded={expanded}
        aria-controls={contentId}
      >
        <div
          className={`tool-icon${classStatus ? ` ${classStatus}` : ""}`}
          dangerouslySetInnerHTML={{ __html: iconHtml }}
        />
        <div
          className={`tool-title${classStatus ? ` ${classStatus}` : ""}`}
          dangerouslySetInnerHTML={{ __html: formattedTitle }}
        />
        <div className="tool-spacer" />
        {intent && <div className="tool-intent">{intent}</div>}
        <div
          className="collapse-indicator"
          dangerouslySetInnerHTML={{ __html: plus }}
        />
      </button>
      <div
        className={`card-body bslib-gap-spacing html-fill-item html-fill-container${expanded ? "" : " collapsed"}`}
        id={contentId}
        role="region"
        aria-labelledby={headerId}
        inert={expanded ? undefined : ("" as unknown as boolean)}
      >
        {children}
      </div>
    </div>
  )
}
