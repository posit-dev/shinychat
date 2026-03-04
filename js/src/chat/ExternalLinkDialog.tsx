import { createRoot } from "react-dom/client"
import { useRef, useEffect } from "react"

declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

interface ExternalLinkDialogProps {
  url: string
  onProceed: () => void
  onAlways: () => void
  onCancel: () => void
}

function ExternalLinkDialogComponent({
  url,
  onProceed,
  onAlways,
  onCancel,
}: ExternalLinkDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return

    try {
      dialog.showModal()
    } catch {
      // If showModal fails, fall back to proceeding
      onProceed()
    }

    // Close dialog when clicking the backdrop (outside the modal content)
    const handleClick = (e: MouseEvent) => {
      if (e.target === dialog) {
        onCancel()
      }
    }
    dialog.addEventListener("click", handleClick)
    return () => dialog.removeEventListener("click", handleClick)
  }, [onProceed, onCancel])

  return (
    <dialog
      ref={dialogRef}
      id="shinychat-external-link-dialog"
      className="shinychat-external-link-dialog"
    >
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

let singletonContainer: HTMLDivElement | null = null
let singletonRoot: ReturnType<typeof createRoot> | null = null

function getOrCreateContainer(): {
  container: HTMLDivElement
  root: ReturnType<typeof createRoot>
} {
  if (!singletonContainer || !singletonRoot) {
    singletonContainer = document.createElement("div")
    singletonContainer.id = "shinychat-external-link-dialog-root"
    document.body.appendChild(singletonContainer)
    singletonRoot = createRoot(singletonContainer)
  }
  return { container: singletonContainer, root: singletonRoot }
}

/**
 * Shows a confirmation dialog for external links.
 * @param url The URL to confirm
 * @returns A promise that resolves to true if confirmed, false otherwise
 */
export function showExternalLinkConfirmation(url: string): Promise<boolean> {
  // Check if the browser supports HTMLDialogElement
  if (typeof window.HTMLDialogElement === "undefined") {
    return Promise.resolve(true)
  }

  // If the user has opted to always open external links, resolve immediately
  if (window.shinychat_always_open_external_links) {
    return Promise.resolve(true)
  }

  return new Promise<boolean>((resolve) => {
    const { root } = getOrCreateContainer()

    const unmount = () => {
      root.render(<></>)
    }

    const handleProceed = () => {
      unmount()
      resolve(true)
    }

    const handleAlways = () => {
      window.shinychat_always_open_external_links = true
      handleProceed()
    }

    const handleCancel = () => {
      unmount()
      resolve(false)
    }

    root.render(
      <ExternalLinkDialogComponent
        url={url}
        onProceed={handleProceed}
        onAlways={handleAlways}
        onCancel={handleCancel}
      />,
    )
  })
}
