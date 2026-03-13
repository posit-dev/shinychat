import { useRef, useEffect } from "react"

interface ExternalLinkDialogProps {
  url: string
  onProceed: () => void
  onAlways: () => void
  onCancel: () => void
}

export function ExternalLinkDialogComponent({
  url,
  onProceed,
  onAlways,
  onCancel,
}: ExternalLinkDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const onProceedRef = useRef(onProceed)
  onProceedRef.current = onProceed
  const onCancelRef = useRef(onCancel)
  onCancelRef.current = onCancel

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    try {
      dialog.showModal()
    } catch {
      // If showModal fails, fall back to proceeding
      onProceedRef.current()
    }

    // Close dialog when clicking the backdrop (outside the modal content)
    const handleClick = (e: MouseEvent) => {
      if (e.target === dialog) {
        onCancelRef.current()
      }
    }
    dialog.addEventListener("click", handleClick)
    return () => dialog.removeEventListener("click", handleClick)
  }, [])

  return (
    <dialog ref={dialogRef} className="shinychat-external-link-dialog">
      <div className="modal position-relative d-block fade show">
        <div className="modal-content">
          <div className="modal-header">
            <h5 className="modal-title">External Link</h5>
            <button
              className="btn-close shinychat-btn-close"
              data-bs-dismiss="modal"
              aria-label="Close"
              onClick={onCancel}
            />
          </div>
          <div className="modal-body">
            <p>This link will take you to an external website:</p>
            <p className="link-url text-break">{url}</p>
          </div>
          <div className="modal-footer flex-wrap-reverse">
            <button
              className="btn btn-sm btn-link shinychat-btn-always ps-0 me-auto"
              onClick={onAlways}
            >
              Always open external links
            </button>
            <div className="d-flex gap-2 justify-content-end">
              <button
                autoFocus
                className="btn btn-sm btn-primary shinychat-btn-proceed"
                onClick={onProceed}
              >
                Open Link
              </button>
              <button
                className="btn btn-sm btn-outline-danger shinychat-btn-cancel"
                onClick={onCancel}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      </div>
    </dialog>
  )
}
