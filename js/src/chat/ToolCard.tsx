import { useState, useMemo, type ReactNode, type Ref } from "react"
import { wrenchAdjustable, plus } from "../utils/icons"
import { fullscreenEnter } from "./useFullscreen"
import { RawHTML } from "./RawHTML"

const plusDSIH = { __html: plus }
const fullscreenEnterDSIH = { __html: fullscreenEnter }

export interface ToolCardProps {
  requestId: string
  toolName: string
  toolTitle?: string
  intent?: string
  icon?: string
  classStatus?: string
  titleTemplate?: string
  fullScreen?: boolean
  initialExpanded?: boolean
  footer?: string
  onEnterFullscreen?: (trigger: HTMLElement) => void
  cardRef?: Ref<HTMLDivElement>
  children?: ReactNode
}

function formatTitle(
  toolName: string,
  toolTitle: string | undefined,
  titleTemplate: string,
): ReactNode {
  const displayName = toolTitle || `${toolName}()`
  const titleSpan = <span className="tool-title-name">{displayName}</span>
  const [before, after] = titleTemplate.split("{title}")
  return (
    <>
      {before}
      {titleSpan}
      {after}
    </>
  )
}

export function ToolCard({
  requestId,
  toolName,
  toolTitle,
  intent,
  icon,
  classStatus = "",
  titleTemplate = "{title}",
  fullScreen = false,
  initialExpanded = false,
  footer,
  onEnterFullscreen,
  cardRef,
  children,
}: ToolCardProps) {
  const [expanded, setExpanded] = useState(initialExpanded)

  const headerId = `tool-header-${requestId}`
  const contentId = `tool-content-${requestId}`
  const iconHtml = icon || wrenchAdjustable
  const formattedTitle = formatTitle(toolName, toolTitle, titleTemplate)

  // Memoize dangerouslySetInnerHTML objects so React 19 sees stable
  // references and skips unnecessary innerHTML resets on re-render.
  const iconDSIH = useMemo(() => ({ __html: iconHtml }), [iconHtml])

  function handleClick(e: React.MouseEvent) {
    e.preventDefault()
    const card = e.currentTarget.closest(".shiny-tool-card")
    if (card?.hasAttribute("fullscreen")) return

    setExpanded(!expanded)
    requestAnimationFrame(() => window.dispatchEvent(new Event("resize")))
  }

  function handleFullscreenClick(e: React.MouseEvent<HTMLButtonElement>) {
    e.preventDefault()
    e.stopPropagation()
    setExpanded(true)
    onEnterFullscreen?.(e.currentTarget)
  }

  return (
    <div
      ref={cardRef}
      className="shiny-tool-card card bslib-card html-fill-item html-fill-container m-0"
    >
      <button
        className="card-header"
        id={headerId}
        onClick={handleClick}
        aria-expanded={expanded}
        aria-controls={contentId}
      >
        <div
          className={`tool-icon${classStatus ? ` ${classStatus}` : ""}`}
          dangerouslySetInnerHTML={iconDSIH}
        />
        <div className={`tool-title${classStatus ? ` ${classStatus}` : ""}`}>
          {formattedTitle}
        </div>
        <div className="tool-spacer" />
        {intent && <div className="tool-intent">{intent}</div>}
        <div
          className="collapse-indicator"
          dangerouslySetInnerHTML={plusDSIH}
        />
      </button>
      <div
        className={`card-body bslib-gap-spacing html-fill-item html-fill-container${expanded ? "" : " collapsed"}`}
        id={contentId}
        role="region"
        aria-labelledby={headerId}
        inert={!expanded || undefined}
      >
        {children}
        {fullScreen && onEnterFullscreen && (
          <button
            className="tool-fullscreen-toggle badge rounded-pill"
            onClick={handleFullscreenClick}
            aria-label="Expand card"
            aria-controls={contentId}
            type="button"
            dangerouslySetInnerHTML={fullscreenEnterDSIH}
          />
        )}
      </div>
      {footer && (
        <RawHTML
          html={footer}
          className="card-footer"
          displayContents={false}
        />
      )}
    </div>
  )
}
