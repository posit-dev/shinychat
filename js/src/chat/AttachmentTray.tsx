import { memo } from "react"
import type { AttachmentStaging } from "./useAttachmentStaging"
import {
  formatBytes,
  acceptAttribute,
  attachmentBadgeLabel,
  type AttachedFile,
} from "./attachments"
import { TextAttachmentPreview } from "./TextAttachmentPreview"
import { plusThin } from "../utils/icons"

export interface AttachmentTrayProps {
  staging: AttachmentStaging
  uploadAccept: string[]
  maxUploadSize: number | null
  enableUpload?: boolean
  disabled?: boolean
}

export const AttachmentTray = memo(function AttachmentTray({
  staging,
  uploadAccept,
  maxUploadSize,
  enableUpload,
  disabled,
}: AttachmentTrayProps) {
  const {
    attachments,
    downscaleNotice,
    gifConvertedNotice,
    sizeNotice,
    fileInputRef,
    attachmentRefs,
    removeAttachmentByKeyboard,
    onFilePick,
    onAttachmentsMouseDown,
  } = staging

  return (
    <>
      {attachments.length > 0 && (
        <div
          className="shiny-chat-input-attachments"
          onMouseDown={onAttachmentsMouseDown}
        >
          {attachments.map((a, i) => (
            <AttachmentPreview
              key={a.id}
              attachment={a}
              index={i}
              onRemove={() => removeAttachmentByKeyboard(i)}
              registerRef={(el) => {
                attachmentRefs.current[i] = el
              }}
            />
          ))}
        </div>
      )}
      {(downscaleNotice || sizeNotice || gifConvertedNotice) && (
        <div className="shiny-chat-input-notice" role="status">
          {sizeNotice && maxUploadSize !== null && (
            <div>
              Attachments exceed the {formatBytes(maxUploadSize)} limit.
            </div>
          )}
          {downscaleNotice && <div>Large image(s) were downscaled to fit.</div>}
          {gifConvertedNotice && (
            <div>Animated GIF(s) were converted to a still image.</div>
          )}
        </div>
      )}
      {enableUpload && (
        <>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={acceptAttribute(uploadAccept)}
            style={{ display: "none" }}
            onChange={onFilePick}
            data-shiny-no-bind-input
          />
          <button
            type="button"
            className="shiny-chat-btn-attach"
            title="Attach file"
            aria-label="Attach file"
            disabled={disabled}
            onClick={() => fileInputRef.current?.click()}
            dangerouslySetInnerHTML={{ __html: plusThin }}
          />
        </>
      )}
    </>
  )
})

const AttachmentPreview = memo(function AttachmentPreview({
  attachment,
  index,
  onRemove,
  registerRef,
}: {
  attachment: AttachedFile
  index: number
  onRemove: () => void
  registerRef: (el: HTMLDivElement | null) => void
}) {
  // Shared focus/keyboard behavior applied to whichever root each variant
  // renders: a single tab stop per attachment, click-to-focus, and
  // Delete/Backspace to remove while focused.
  const containerProps: React.HTMLAttributes<HTMLDivElement> = {
    tabIndex: 0,
    "aria-label": attachment.name
      ? `Attachment: ${attachment.name}. Press Delete to remove.`
      : "Attachment. Press Delete to remove.",
    onClick: (e) => (e.currentTarget as HTMLDivElement).focus(),
    onKeyDown: (e) => {
      if (e.code === "Delete" || e.code === "Backspace") {
        e.preventDefault()
        onRemove()
      }
    },
  }

  if (attachment.family === "image") {
    return (
      <div
        ref={registerRef}
        className="shiny-chat-input-thumbnail"
        title={attachment.name || undefined}
        {...containerProps}
      >
        <img
          src={attachment.dataUrl}
          alt={
            attachment.name
              ? `Attached image: ${attachment.name}`
              : `Attached image ${index + 1}`
          }
        />
        <button
          type="button"
          tabIndex={0}
          aria-label={
            attachment.name ? `Remove ${attachment.name}` : "Remove image"
          }
          onClick={onRemove}
        >
          ×
        </button>
      </div>
    )
  }
  if (attachment.family === "text") {
    return (
      <TextAttachmentPreview
        dataUrl={attachment.dataUrl}
        name={attachment.name}
        size={attachment.size}
        onRemove={onRemove}
        rootRef={registerRef}
        rootProps={containerProps}
      />
    )
  }
  return (
    <div
      ref={registerRef}
      className="shiny-chat-input-attachment-chip"
      title={attachment.name || undefined}
      {...containerProps}
    >
      <span className="shiny-chat-attachment-badge">
        {attachmentBadgeLabel(attachment.name, attachment.type)}
      </span>
      <span className="shiny-chat-attachment-meta">
        <span className="shiny-chat-attachment-name">
          {attachment.name || "attachment"}
        </span>
        <span className="shiny-chat-attachment-size">
          {formatBytes(attachment.size)}
        </span>
      </span>
      <button
        type="button"
        tabIndex={0}
        aria-label={
          attachment.name ? `Remove ${attachment.name}` : "Remove attachment"
        }
        onClick={onRemove}
      >
        ×
      </button>
    </div>
  )
})
