import { useState, useEffect, useRef, memo } from "react"
import type { ChatMessageData } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { chatTagToComponentMap } from "./chatTagToComponentMap"

interface ThinkingDisplayProps {
  message: ChatMessageData
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className="shinychat-thinking-chevron"
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      aria-hidden="true"
      style={{
        transform: expanded ? "rotate(90deg)" : "rotate(0deg)",
        transition: "transform 0.15s ease",
      }}
    >
      <path
        d="M4.5 2.5L8 6L4.5 9.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export const ThinkingDisplay = memo(function ThinkingDisplay({
  message,
}: ThinkingDisplayProps) {
  const [expanded, setExpanded] = useState(false)
  const [userToggled, setUserToggled] = useState(false)
  const prevStreamingRef = useRef(message.streaming)

  // Auto-collapse when thinking completes (unless user has re-expanded after)
  useEffect(() => {
    if (prevStreamingRef.current && !message.streaming && !userToggled) {
      const timer = setTimeout(() => setExpanded(false), 600)
      return () => clearTimeout(timer)
    }
    prevStreamingRef.current = message.streaming
  }, [message.streaming, userToggled])

  const handleToggle = () => {
    setExpanded((prev) => !prev)
    if (!message.streaming) {
      setUserToggled(true)
    }
  }

  const headerText = getHeaderText(message)

  return (
    <div
      className="shinychat-thinking"
      data-streaming={message.streaming || undefined}
    >
      <button
        className="shinychat-thinking-header"
        onClick={handleToggle}
        aria-expanded={expanded}
        aria-controls={`thinking-content-${message.id}`}
      >
        <ChevronIcon expanded={expanded} />
        <span className="shinychat-thinking-label">{headerText}</span>
        {message.streaming && (
          <span className="shinychat-thinking-dots" aria-hidden="true">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </span>
        )}
      </button>
      {expanded && (
        <div
          className="shinychat-thinking-content"
          id={`thinking-content-${message.id}`}
          role="region"
          aria-labelledby={`thinking-header-${message.id}`}
        >
          <MarkdownContent
            content={message.content}
            contentType="markdown"
            role="assistant"
            streaming={message.streaming}
            tagToComponentMap={chatTagToComponentMap}
          />
        </div>
      )}
    </div>
  )
})

function getHeaderText(message: ChatMessageData): string {
  if (message.streaming) {
    return message.topic ? `${message.topic}` : "Thinking"
  }
  if (message.durationMs != null && message.durationMs > 0) {
    const seconds = Math.round(message.durationMs / 1000)
    if (seconds < 1) return "Thought for less than a second"
    return `Thought for ${seconds}s`
  }
  return "Thinking"
}
