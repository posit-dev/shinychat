import { useState, useMemo, useId, type ReactNode, type Ref } from "react"
import { bareDot, plus } from "../utils/icons"
import { fullscreenEnter } from "./useFullscreen"
import { RawHTML } from "./RawHTML"

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

const plusDSIH = { __html: plus }
const fullscreenEnterDSIH = { __html: fullscreenEnter }

export interface ToolCardProps {
  toolName: string
  toolTitle?: string
  /** The per-call identifying value, appended as "{title}: {label}". */
  label?: string
  intent?: string
  icon?: string
  classStatus?: string
  /** A short text status cue (e.g. "failed") shown in the header, so status is not conveyed by color alone. */
  statusNote?: string
  fullScreen?: boolean
  initialExpanded?: boolean
  footer?: string
  onEnterFullscreen?: (trigger: HTMLElement) => void
  cardRef?: Ref<HTMLDivElement>
  children?: ReactNode
}

export function ToolCard({
  toolName,
  toolTitle,
  label,
  intent,
  icon,
  classStatus = "",
  statusNote,
  fullScreen = false,
  initialExpanded = false,
  footer,
  onEnterFullscreen,
  cardRef,
  children,
}: ToolCardProps) {
  const [expanded, setExpanded] = useState(initialExpanded)

  // Not derived from the tool's `request-id`: that is optional in routed
  // content (anonymous calls get a loop-local synthetic id) and can repeat
  // across messages, which would produce duplicate document ids.
  const uid = useId()
  const headerId = `tool-header${uid}`
  const contentId = `tool-content${uid}`
  const iconHtml = icon || bareDot
  const displayName = toolTitle || `${toolName}()`
  const labelPart = label
    ? `: <span class="tool-title-label">${escapeHtml(label)}</span>`
    : ""
  const formattedTitle = `<span class="tool-title-name">${displayName}</span>${labelPart}`

  // Memoize dangerouslySetInnerHTML objects so React 19 sees stable
  // references and skips unnecessary innerHTML resets on re-render.
  const iconDSIH = useMemo(() => ({ __html: iconHtml }), [iconHtml])
  const titleDSIH = useMemo(
    () => ({ __html: formattedTitle }),
    [formattedTitle],
  )

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
        <div
          className={`tool-title${classStatus ? ` ${classStatus}` : ""}`}
          dangerouslySetInnerHTML={titleDSIH}
        />
        {statusNote && (
          <div
            className={`tool-status-note${classStatus ? ` ${classStatus}` : ""}`}
          >
            {statusNote}
          </div>
        )}
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
          fillable={false}
        />
      )}
    </div>
  )
}
