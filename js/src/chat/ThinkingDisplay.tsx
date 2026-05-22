import {
  useState,
  useEffect,
  useRef,
  memo,
  useCallback,
  useLayoutEffect,
} from "react"
import { useStickToBottom } from "use-stick-to-bottom"
import type { ThinkingBlock } from "./state"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { chatTagToComponentMap } from "./chatTagToComponentMap"
import { useChatStopScroll } from "./context"
import { usePrefersReducedMotion } from "./usePrefersReducedMotion"

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
  const reducedMotion = usePrefersReducedMotion()
  const [visible, setVisible] = useState(text)
  const [fading, setFading] = useState(false)
  const pendingText = useRef(text)

  useLayoutEffect(() => {
    if (text === visible) return
    pendingText.current = text

    if (reducedMotion) {
      setVisible(text)
      setFading(false)
      return
    }

    setFading(true)
    const timer = setTimeout(() => {
      setVisible(pendingText.current)
      setFading(false)
    }, FADE_DURATION_MS)

    return () => clearTimeout(timer)
  }, [text, visible, reducedMotion])

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
  const outerStopScroll = useChatStopScroll()

  const {
    scrollRef: innerScrollRef,
    contentRef: innerContentRef,
    scrollToBottom: innerScrollToBottom,
  } = useStickToBottom({ resize: "smooth" })

  // When the inner container transitions from non-overflowing to overflowing,
  // kick stick-to-bottom into gear so it follows the stream.
  const wasOverflowing = useRef(false)
  useEffect(() => {
    const el = innerScrollRef.current
    if (!el || !expanded || !thinking.streaming) return
    const isOverflowing = el.scrollHeight > el.clientHeight
    if (isOverflowing && !wasOverflowing.current) {
      innerScrollToBottom()
    }
    wasOverflowing.current = isOverflowing
  }, [
    thinking.content,
    expanded,
    thinking.streaming,
    innerScrollToBottom,
    innerScrollRef,
  ])

  const displayedTopic = useDisplayedTopic(
    thinking.streaming ? thinking.topic : null,
  )

  // Auto-collapse when thinking completes (unless user has re-expanded after)
  useEffect(() => {
    if (prevStreamingRef.current && !thinking.streaming) {
      if (!userToggled) {
        const timer = setTimeout(() => setExpanded(false), 600)
        return () => clearTimeout(timer)
      }
      prevStreamingRef.current = thinking.streaming
    }
    prevStreamingRef.current = thinking.streaming
  }, [thinking.streaming, userToggled])

  const handleToggle = useCallback(() => {
    setExpanded((prev) => {
      if (prev) {
        outerStopScroll?.()
      } else if (thinking.streaming) {
        wasOverflowing.current = false
        innerScrollToBottom()
      }
      return !prev
    })
    if (!thinking.streaming) {
      setUserToggled(true)
    }
  }, [thinking.streaming, outerStopScroll, innerScrollToBottom])

  const headerText = getHeaderText(thinking, displayedTopic)
  const { visible: labelText, fading: labelFading } = useFadingText(headerText)

  if (!thinking.streaming && !thinking.content.trim()) {
    return null
  }

  return (
    <div
      className="shinychat-thinking"
      data-streaming={thinking.streaming || undefined}
    >
      <button
        id={`thinking-header-${messageId}`}
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
          <svg
            className="shinychat-thinking-dot"
            width="8"
            height="8"
            xmlns="http://www.w3.org/2000/svg"
            aria-hidden="true"
          >
            <circle cx="4" cy="4" r="4" />
          </svg>
        )}
      </button>
      <div
        className="shinychat-thinking-content"
        id={`thinking-content-${messageId}`}
        role="region"
        aria-labelledby={`thinking-header-${messageId}`}
        aria-hidden={!expanded ? "true" : undefined}
        inert={!expanded || undefined}
        data-expanded={expanded || undefined}
      >
        <div className="shinychat-thinking-content-inner" ref={innerScrollRef}>
          <div ref={innerContentRef}>
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
  if (thinking.durationMs != null && thinking.durationMs >= 500) {
    const seconds = Math.round(thinking.durationMs / 1000)
    if (seconds < 1) return "Thought for less than a second"
    return `Thought for ${seconds}s`
  }
  return "Thinking"
}
