import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useCallback,
  useState,
} from "react"
import { createPortal } from "react-dom"
import {
  attachmentFamily,
  dataUrlToBlob,
  decodeTextDataUrl,
} from "./attachments"

const FOCUSABLE_SELECTOR =
  'button, [tabindex="0"], a[href], input, select, textarea, iframe'

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
  const dialogRef = useRef<HTMLDivElement>(null)
  const text = useMemo(
    () => (isText ? decodeTextDataUrl(src) : ""),
    [isText, src],
  )

  useLayoutEffect(() => {
    dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus()
  }, [])

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key === "Escape") {
        onClose()
        return
      }
      if (e.key !== "Tab") return
      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
      if (focusable.length === 0) return
      const first = focusable[0]!
      const last = focusable[focusable.length - 1]!
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    },
    [onClose],
  )

  // A Blob URL is more robust than a multi-MB base64 data URL as an iframe src.
  useEffect(() => {
    if (isImage || isText) return
    const url = URL.createObjectURL(dataUrlToBlob(src))
    setPdfUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [src, isImage, isText])

  return createPortal(
    <div
      ref={dialogRef}
      className="shiny-chat-lightbox"
      role="dialog"
      aria-modal="true"
      aria-label={name || "Attachment preview"}
      onClick={onClose}
      onKeyDown={onKeyDown}
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
