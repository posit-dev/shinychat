import {
  useState,
  useEffect,
  useRef,
  memo,
  useCallback,
  useLayoutEffect,
} from "react"
import type { ThinkingBlock } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { chatTagToComponentMap } from "./chatTagToComponentMap"

interface ThinkingDisplayProps {
  thinking: ThinkingBlock
  messageId: string
}

const TOPIC_MIN_DISPLAY_MS = 2500

function useDisplayedTopic(topic: string | null | undefined): string | null {
  const [displayed, setDisplayed] = useState<string | null>(null)
  const lastSetAt = useRef(0)
  const pendingTopic = useRef<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (!topic) return

    const now = Date.now()
    const elapsed = now - lastSetAt.current

    if (elapsed >= TOPIC_MIN_DISPLAY_MS || !displayed) {
      setDisplayed(topic)
      lastSetAt.current = now
      pendingTopic.current = null
    } else {
      pendingTopic.current = topic
      if (!timerRef.current) {
        const remaining = TOPIC_MIN_DISPLAY_MS - elapsed
        timerRef.current = setTimeout(() => {
          timerRef.current = null
          if (pendingTopic.current) {
            setDisplayed(pendingTopic.current)
            lastSetAt.current = Date.now()
            pendingTopic.current = null
          }
        }, remaining)
      }
    }

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
    }
  }, [topic, displayed])

  return displayed
}

const FADE_DURATION_MS = 200

function useFadingText(text: string): { visible: string; fading: boolean } {
  const [visible, setVisible] = useState(text)
  const [fading, setFading] = useState(false)
  const pendingText = useRef(text)

  useLayoutEffect(() => {
    if (text === visible) return
    pendingText.current = text
    setFading(true)

    const timer = setTimeout(() => {
      setVisible(pendingText.current)
      setFading(false)
    }, FADE_DURATION_MS)

    return () => clearTimeout(timer)
  }, [text, visible])

  return { visible, fading }
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
      {...(expanded ? { "data-expanded": "" } : {})}
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
  thinking,
  messageId,
}: ThinkingDisplayProps) {
  const [expanded, setExpanded] = useState(false)
  const [userToggled, setUserToggled] = useState(false)
  const prevStreamingRef = useRef(thinking.streaming)

  const displayedTopic = useDisplayedTopic(
    thinking.streaming ? thinking.topic : null,
  )

  // Auto-collapse when thinking completes (unless user has re-expanded after)
  useEffect(() => {
    if (prevStreamingRef.current && !thinking.streaming && !userToggled) {
      const timer = setTimeout(() => setExpanded(false), 600)
      return () => clearTimeout(timer)
    }
    prevStreamingRef.current = thinking.streaming
  }, [thinking.streaming, userToggled])

  const handleToggle = useCallback(() => {
    setExpanded((prev) => !prev)
    if (!thinking.streaming) {
      setUserToggled(true)
    }
  }, [thinking.streaming])

  const headerText = getHeaderText(thinking, displayedTopic)
  const { visible: labelText, fading: labelFading } = useFadingText(headerText)

  return (
    <div
      className="shinychat-thinking"
      data-streaming={thinking.streaming || undefined}
    >
      <button
        className="shinychat-thinking-header"
        onClick={handleToggle}
        aria-expanded={expanded}
        aria-controls={`thinking-content-${messageId}`}
      >
        <ChevronIcon expanded={expanded} />
        <span
          className="shinychat-thinking-label"
          data-fading={labelFading || undefined}
        >
          {labelText}
        </span>
        {thinking.streaming && (
          <span className="shinychat-thinking-dots" aria-hidden="true">
            <span className="dot" />
            <span className="dot" />
            <span className="dot" />
          </span>
        )}
      </button>
      <div
        className="shinychat-thinking-content"
        id={`thinking-content-${messageId}`}
        role="region"
        aria-labelledby={`thinking-header-${messageId}`}
        aria-hidden={!expanded}
        data-expanded={expanded || undefined}
      >
        <div className="shinychat-thinking-content-inner">
          <MarkdownContent
            content={thinking.content}
            contentType="markdown"
            role="assistant"
            streaming={thinking.streaming}
            tagToComponentMap={chatTagToComponentMap}
          />
        </div>
      </div>
    </div>
  )
})

function getHeaderText(
  thinking: ThinkingBlock,
  displayedTopic: string | null,
): string {
  if (thinking.streaming) {
    return displayedTopic ?? "Thinking"
  }
  if (thinking.durationMs != null && thinking.durationMs > 0) {
    const seconds = Math.round(thinking.durationMs / 1000)
    if (seconds < 1) return "Thought for less than a second"
    return `Thought for ${seconds}s`
  }
  return "Thinking"
}
