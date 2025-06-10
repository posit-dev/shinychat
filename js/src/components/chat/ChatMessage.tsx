import { useEffect, useRef } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import { MarkdownStream } from "../MarkdownStream"
import type { ContentType } from "./types"

export interface ChatMessageProps {
  content: string
  contentType?: ContentType
  streaming?: boolean
  icon?: string
  onContentChange?: () => void
  onStreamEnd?: () => void
}

const ICONS = {
  robot: (
    <svg
      fill="currentColor"
      className="bi bi-robot"
      viewBox="0 0 16 16"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path d="M6 12.5a.5.5 0 0 1 .5-.5h3a.5.5 0 0 1 0 1h-3a.5.5 0 0 1-.5-.5M3 8.062C3 6.76 4.235 5.765 5.53 5.886a26.6 26.6 0 0 0 4.94 0C11.765 5.765 13 6.76 13 8.062v1.157a.93.93 0 0 1-.765.935c-.845.147-2.34.346-4.235.346s-3.39-.2-4.235-.346A.93.93 0 0 1 3 9.219zm4.542-.827a.25.25 0 0 0-.217.068l-.92.9a25 25 0 0 1-1.871-.183.25.25 0 0 0-.068.495c.55.076 1.232.149 2.02.193a.25.25 0 0 0 .189-.071l.754-.736.847 1.71a.25.25 0 0 0 .404.062l.932-.97a25 25 0 0 0 1.922-.188.25.25 0 0 0-.068-.495c-.538.074-1.207.145-1.98.189a.25.25 0 0 0-.166.076l-.754.785-.842-1.7a.25.25 0 0 0-.182-.135" />
      <path d="M8.5 1.866a1 1 0 1 0-1 0V3h-2A4.5 4.5 0 0 0 1 7.5V8a1 1 0 0 0-1 1v2a1 1 0 0 0 1 1v1a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-1a1 1 0 0 0 1-1V9a1 1 0 0 0-1-1v-.5A4.5 4.5 0 0 0 10.5 3h-2zM14 7.5V13a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V7.5A3.5 3.5 0 0 1 5.5 4h5A3.5 3.5 0 0 1 14 7.5" />
    </svg>
  ),
  dots_fade: (
    <svg
      width="24"
      height="24"
      fill="currentColor"
      viewBox="0 0 24 24"
      xmlns="http://www.w3.org/2000/svg"
    >
      <style>
        {`.spinner_S1WN{animation:spinner_MGfb .8s linear infinite;animation-delay:-.8s}.spinner_Km9P{animation-delay:-.65s}.spinner_JApP{animation-delay:-.5s}@keyframes spinner_MGfb{93.75%,100%{opacity:.2}}`}
      </style>
      <circle className="spinner_S1WN" cx="4" cy="12" r="3" />
      <circle className="spinner_S1WN spinner_Km9P" cx="12" cy="12" r="3" />
      <circle className="spinner_S1WN spinner_JApP" cx="20" cy="12" r="3" />
    </svg>
  ),
}

export function ChatMessage({
  content,
  contentType = "markdown",
  streaming = false,
  icon,
  onContentChange,
  onStreamEnd,
}: ChatMessageProps): JSX.Element {
  const messageRef = useRef<HTMLDivElement>(null)

  // Show dots until we have content
  const isEmpty = content.trim().length === 0

  // Render the icon
  const renderIcon = () => {
    if (isEmpty) {
      return ICONS.dots_fade
    }

    if (icon) {
      // If icon is provided as HTML string, render it
      if (typeof icon === "string" && icon.includes("<")) {
        return <div dangerouslySetInnerHTML={{ __html: icon }} />
      }
      // Otherwise treat it as text/URL (could be extended for image URLs)
      return <div>{icon}</div>
    }

    return ICONS.robot
  }

  // Handle content changes and make suggestions accessible
  const handleContentChange = () => {
    onContentChange?.()
    if (!streaming) {
      makeSuggestionsAccessible()
    }
  }

  const handleStreamEnd = () => {
    onStreamEnd?.()
    makeSuggestionsAccessible()
  }

  const makeSuggestionsAccessible = () => {
    if (!messageRef.current) return

    messageRef.current
      .querySelectorAll(".suggestion,[data-suggestion]")
      .forEach((el) => {
        if (!(el instanceof HTMLElement)) return
        if (el.hasAttribute("tabindex")) return

        el.setAttribute("tabindex", "0")
        el.setAttribute("role", "button")

        const suggestion = el.dataset.suggestion || el.textContent
        el.setAttribute("aria-label", `Use chat suggestion: ${suggestion}`)
      })
  }

  // Make suggestions accessible when content changes
  useEffect(() => {
    if (!streaming) {
      makeSuggestionsAccessible()
    }
  }, [content, streaming])

  return (
    <div ref={messageRef} className="chat-message">
      <div className="message-icon">{renderIcon()}</div>
      <MarkdownStream
        content={content}
        contentType={contentType}
        streaming={streaming}
        autoScroll
        onContentChange={handleContentChange}
        onStreamEnd={handleStreamEnd}
      />
    </div>
  )
}
