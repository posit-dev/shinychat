/**
 * Shared copy-to-clipboard affordance for code blocks. Used by both paths
 * that render `<pre><code>`: the markdown pipeline (CopyableCodeBlock, a
 * React component) and RawHTML content (post-mount DOM injection, e.g. the
 * tool-result details slot), which React deliberately does not manage.
 */

export const COPY_BUTTON_CLASS = "code-copy-button"
const CHECKED_CLASS = "code-copy-button-checked"
const CHECKED_MS = 2000

export async function copyTextToClipboard(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // Fallback for iframes without clipboard-write permission
    const ta = document.createElement("textarea")
    ta.value = text
    ta.style.position = "fixed"
    ta.style.opacity = "0"
    document.body.appendChild(ta)
    ta.select()
    document.execCommand("copy")
    document.body.removeChild(ta)
  }
}

/** Mark the button as copied for 2s; returns a cancel for re-flash/unmount. */
export function flashCopied(button: HTMLElement): () => void {
  button.classList.add(CHECKED_CLASS)
  const timer = setTimeout(
    () => button.classList.remove(CHECKED_CLASS),
    CHECKED_MS,
  )
  return () => clearTimeout(timer)
}

/** The DOM-side button; the markdown pipeline renders the same markup as JSX. */
export function createCopyButton(): HTMLButtonElement {
  const button = document.createElement("button")
  // Explicit, like the JSX twin: the default is "submit", which would
  // submit an enclosing form on click.
  button.type = "button"
  button.className = COPY_BUTTON_CLASS
  button.title = "Copy to clipboard"
  button.setAttribute("aria-label", "Copy to clipboard")
  const icon = document.createElement("i")
  icon.className = "bi"
  button.appendChild(icon)
  return button
}
