import { memo, useMemo } from "react"
import { previewText, formatBytes, TEXT_PREVIEW_MAX_CHARS } from "./attachments"

export const TextAttachmentPreview = memo(function TextAttachmentPreview({
  dataUrl,
  name,
  size,
  onRemove,
  onActivate,
  rootRef,
  rootProps,
}: {
  dataUrl: string
  name: string
  size: number
  onRemove?: () => void
  /** When set, the card is a clickable button that opens the full-text lightbox
   * (sent-message use). Mutually exclusive with rootProps. */
  onActivate?: () => void
  /** Ref + props the staged-input tray uses to make the card focusable. */
  rootRef?: (el: HTMLDivElement | null) => void
  rootProps?: React.HTMLAttributes<HTMLDivElement>
}) {
  const text = useMemo(
    () => previewText(dataUrl, TEXT_PREVIEW_MAX_CHARS).trim(),
    [dataUrl],
  )
  const activationProps: React.HTMLAttributes<HTMLDivElement> | undefined =
    onActivate
      ? {
          role: "button",
          tabIndex: 0,
          onClick: onActivate,
          onKeyDown: (e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault()
              onActivate()
            }
          },
        }
      : undefined
  return (
    <div
      ref={rootRef}
      className="shiny-chat-text-preview"
      title={name || undefined}
      {...rootProps}
      {...activationProps}
    >
      <div className="shiny-chat-text-preview-body">
        {text || "(empty file)"}
      </div>
      <div className="shiny-chat-text-preview-footer">
        {name && <span className="shiny-chat-text-preview-name">{name}</span>}
        <span className="shiny-chat-text-preview-size">
          {formatBytes(size)}
        </span>
      </div>
      {onRemove && (
        <button
          type="button"
          tabIndex={0}
          aria-label={name ? `Remove ${name}` : "Remove attachment"}
          onClick={onRemove}
        >
          ×
        </button>
      )}
    </div>
  )
})
