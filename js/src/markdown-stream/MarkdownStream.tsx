import { useState, useRef, useCallback, useEffect } from "react"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { useAutoScroll, findScrollableParent } from "../markdown/useAutoScroll"
import type { ContentType } from "../transport/types"

export interface MarkdownStreamProps {
  initialContent?: string
  initialContentType?: ContentType
  initialStreaming?: boolean
  autoScroll?: boolean
  onApiReady?: (api: MarkdownStreamApi) => void
}

export type MarkdownStreamApi = {
  appendContent: (chunk: string) => void
  replaceContent: (content: string) => void
  setStreaming: (streaming: boolean) => void
  setContentType: (contentType: ContentType) => void
}

/**
 * Standalone MarkdownStream component for the <shiny-markdown-stream> entry point.
 * Manages its own content state (updated via imperative methods from the custom element shell).
 */
export function MarkdownStream({
  initialContent = "",
  initialContentType = "markdown",
  initialStreaming = false,
  autoScroll = false,
  onApiReady,
}: MarkdownStreamProps) {
  const [content, setContent] = useState(initialContent)
  const [contentType, setContentType] =
    useState<ContentType>(initialContentType)
  const [streaming, setStreaming] = useState(initialStreaming)
  const innerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll: the hook gives us a callback ref for the scrollable container.
  // In standalone mode we don't own the scrollable ancestor, so we do a one-time
  // DOM walk on mount and wire the callback ref to the found element.
  const { containerRef, scrollToBottom } = useAutoScroll({
    streaming: autoScroll && streaming,
    contentDependency: content,
  })

  useEffect(() => {
    if (!autoScroll || !innerRef.current) return

    const scrollable = findScrollableParent(innerRef.current)
    if (scrollable) {
      // Attach the hook's callback ref to the discovered scrollable element
      containerRef(scrollable)
    }

    return () => {
      // Detach on unmount
      containerRef(null)
    }
    // Only run once on mount — the scrollable parent doesn't change
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Re-engage auto-scroll when streaming starts
  useEffect(() => {
    if (streaming && autoScroll) {
      scrollToBottom()
    }
  }, [streaming, autoScroll, scrollToBottom])

  const appendContent = useCallback((chunk: string) => {
    setContent((prev) => prev + chunk)
  }, [])

  const replaceContent = useCallback((newContent: string) => {
    setContent(newContent)
  }, [])

  // Notify the shell of the imperative API on mount (intentionally empty deps —
  // the API methods are stable refs and onApiReady only needs to fire once)
  useEffect(() => {
    onApiReady?.({
      appendContent,
      replaceContent,
      setStreaming,
      setContentType,
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div ref={innerRef}>
      <MarkdownContent
        content={content}
        contentType={contentType}
        streaming={streaming}
      />
    </div>
  )
}
