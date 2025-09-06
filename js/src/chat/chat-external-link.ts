declare global {
  interface Window {
    shinychat_always_open_external_links?: boolean
  }
}

export class ExternalLinkDialog {
  url: string | null = null

  private static instance: ExternalLinkDialog | null = null
  private dialog: HTMLDialogElement | null = null
  private resolvePromise: ((value: boolean) => void) | null = null

  static getInstance(): ExternalLinkDialog {
    if (!ExternalLinkDialog.instance) {
      ExternalLinkDialog.instance = new ExternalLinkDialog()
    }
    return ExternalLinkDialog.instance
  }

  constructor() {
    this.createDialog()
  }

  /**
   * Shows a modal dialog asking for confirmation to open an external link
   * @param url The URL to open
   * @returns A promise that resolves to true if the user confirmed, false otherwise
   */
  async showConfirmation(url: string): Promise<boolean> {
    // If the user has opted to always open external links, resolve immediately
    if (window.shinychat_always_open_external_links) {
      return Promise.resolve(true)
    }

    this.url = url

    // Update the URL in the dialog
    const linkUrlElement = this.dialog?.querySelector(".link-url")
    if (linkUrlElement) {
      linkUrlElement.textContent = url
    }

    return new Promise<boolean>((resolve) => {
      this.resolvePromise = resolve

      try {
        this.dialog?.showModal()
      } catch (err) {
        // If showModal fails, resolve with true to fallback to default behavior
        resolve(true)
      }
    })
  }

  private createDialog(): void {
    if (this.dialog) return

    this.dialog = document.createElement("dialog")
    this.dialog.id = "shinychat-external-link-dialog"
    this.dialog.className = "shinychat-external-link-dialog"

    // Create the dialog content with Bootstrap classes
    this.dialog.innerHTML = `
      <div class="modal position-relative d-block fade show">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">External Link</h5>
            <button class="btn-close shinychat-btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
          </div>
          <div class="modal-body">
            <p>This link will take you to an external website:</p>
            <p class="link-url text-break"></p>
          </div>
          <div class="modal-footer flex-wrap-reverse">
            <button class="btn btn-sm btn-link shinychat-btn-always me-auto">Always open external links</button>
            <div class="d-flex gap-2 justify-content-end">
              <button autofocus class="btn btn-sm btn-primary shinychat-btn-proceed">Open Link</button>
              <button class="btn btn-sm btn-outline-danger shinychat-btn-cancel">Cancel</button>
            </div>
          </div>
          </div>
        </div>
      </div>
    `

    document.body.appendChild(this.dialog)

    // Add event listeners to the buttons
    const getBtn = (selector: string) =>
      this.dialog?.querySelector(selector) as HTMLButtonElement

    const btns = {
      close: getBtn(".shinychat-btn-close"),
      cancel: getBtn(".shinychat-btn-cancel"),
      proceed: getBtn(".shinychat-btn-proceed"),
      always: getBtn(".shinychat-btn-always"),
    }

    btns.close.addEventListener("click", () => this.handleCancel())
    btns.cancel.addEventListener("click", () => this.handleCancel())
    btns.proceed.addEventListener("click", () => this.handleProceed())
    btns.always.addEventListener("click", () => this.handleAlways())

    // Close the dialog when clicked outside (native dialog behavior)
    this.dialog.addEventListener("click", (e) => {
      if (e.target === this.dialog) {
        this.handleCancel()
        e.preventDefault()
      }
    })
  }

  private handleCancel(): void {
    this.dialog?.close()
    if (this.resolvePromise) {
      this.resolvePromise(false)
      this.resolvePromise = null
    }
  }

  private handleProceed(): void {
    this.dialog?.close()
    if (this.resolvePromise) {
      this.resolvePromise(true)
      this.resolvePromise = null
    }
  }

  private handleAlways(): void {
    window.shinychat_always_open_external_links = true
    this.handleProceed()
  }
}

/**
 * Shows a confirmation dialog for external links
 * @param url The URL to confirm
 * @returns A promise that resolves to true if confirmed, false otherwise
 */
export function showExternalLinkConfirmation(url: string): Promise<boolean> {
  // Check if the browser supports HTMLDialogElement
  if (typeof window.HTMLDialogElement !== "undefined") {
    const dialog = ExternalLinkDialog.getInstance()
    return dialog.showConfirmation(url)
  }

  // Fallback for browsers without dialog support
  return Promise.resolve(true)
}
