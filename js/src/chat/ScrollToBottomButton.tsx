import { chevronDown } from "../utils/icons"

export interface ScrollToBottomButtonProps {
  isAtBottom: boolean
  scrollToBottom: () => void
  streaming: boolean
}

export function ScrollToBottomButton({
  isAtBottom,
  scrollToBottom,
  streaming,
}: ScrollToBottomButtonProps) {
  if (isAtBottom) return null

  const className = streaming
    ? "shiny-chat-scroll-to-bottom streaming"
    : "shiny-chat-scroll-to-bottom"

  return (
    <button
      type="button"
      className={className}
      title="Scroll to bottom"
      aria-label="Scroll to bottom"
      onClick={() => scrollToBottom()}
    >
      <span dangerouslySetInnerHTML={{ __html: chevronDown }} />
    </button>
  )
}
