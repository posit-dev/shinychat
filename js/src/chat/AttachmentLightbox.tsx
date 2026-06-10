import { useEffect, useMemo, useState } from "react"
import { createPortal } from "react-dom"
import {
  attachmentFamily,
  dataUrlToBlob,
  decodeTextDataUrl,
} from "./attachments"

/**
 * Full-screen overlay showing a single attachment at full size: an <img> for
 * images, the browser's built-in PDF viewer (an <iframe>) for PDFs, or a
 * scrollable monospace <pre> for text files. The file name is shown beneath the
 * preview. Rendered into document.body (via a portal) so it escapes the chat
 * container's overflow and stacking context. Closes on backdrop click, the
 * close button, or Escape.
 */
export function AttachmentLightbox({
  src,
  name,
  mime,
  onClose,
}: {
  src: string
  name: string
  mime: string
  onClose: () => void
}) {
  const family = attachmentFamily(mime)
  const isImage = family === "image"
  const isText = family === "text"
  const [pdfUrl, setPdfUrl] = useState<string | null>(null)
  const text = useMemo(
    () => (isText ? decodeTextDataUrl(src) : ""),
    [isText, src],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  // A Blob URL is more robust than a multi-MB base64 data URL as an iframe src.
  useEffect(() => {
    if (isImage || isText) return
    const url = URL.createObjectURL(dataUrlToBlob(src))
    setPdfUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [src, isImage, isText])

  return createPortal(
    <div
      className="shiny-chat-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={name || "Attachment preview"}
      onClick={onClose}
    >
      <div
        className="shiny-chat-lightbox-content"
        // Clicking the preview/name shouldn't dismiss; only the backdrop does.
        onClick={(e) => e.stopPropagation()}
      >
        {isImage ? (
          <img
            className="shiny-chat-lightbox-img"
            src={src}
            alt={name || "Attached image"}
          />
        ) : isText ? (
          <pre
            className="shiny-chat-lightbox-text"
            tabIndex={0}
            aria-label={name || "File content"}
          >
            {text || "(empty file)"}
          </pre>
        ) : (
          pdfUrl && (
            <iframe
              className="shiny-chat-lightbox-frame"
              src={pdfUrl}
              title={name || "PDF preview"}
            />
          )
        )}
        {name && <div className="shiny-chat-lightbox-name">{name}</div>}
      </div>
      <button
        type="button"
        className="shiny-chat-lightbox-close"
        aria-label="Close preview"
        onClick={onClose}
      >
        ×
      </button>
    </div>,
    document.body,
  )
}
