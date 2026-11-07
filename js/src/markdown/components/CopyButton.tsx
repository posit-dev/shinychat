import { useRef } from "react"
import {
  COPY_BUTTON_CLASS,
  copyTextToClipboard,
  flashCopied,
} from "../../utils/copyButton"

/**
 * The JSX twin of createCopyButton() (DOM land, for RawHTML content React
 * can't reach). `getText` runs at click time so it reads the rendered code.
 */
export function CopyButton({ getText }: { getText: () => string }) {
  const cancelFlash = useRef<(() => void) | undefined>(undefined)

  const handleCopy = async (e: React.MouseEvent<HTMLButtonElement>) => {
    const button = e.currentTarget
    await copyTextToClipboard(getText())
    cancelFlash.current?.()
    cancelFlash.current = flashCopied(button)
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className={COPY_BUTTON_CLASS}
      title="Copy to clipboard"
      aria-label="Copy to clipboard"
    >
      <i className="bi" />
    </button>
  )
}
