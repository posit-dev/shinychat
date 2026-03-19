import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
} from "react"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { useAutoScroll, findScrollableParent } from "../markdown/useAutoScroll"
import type { ContentType } from "../transport/types"

const CHAT_CONTAINER_TAG = "shiny-chat-container"

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

/** Standalone component for the <shiny-markdown-stream> custom element. */
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
  const scrollParentRef = useRef<HTMLElement | null>(null)

  // Auto-scroll: the hook gives us a callback ref for the scrollable container.
  // In standalone mode we don't own the scrollable ancestor, so we do a DOM
  // walk to find it and wire the callback ref to the found element.
  const { containerRef } = useAutoScroll({
    streaming: autoScroll && streaming,
    contentDependency: content,
  })

  useLayoutEffect(() => {
    if (!autoScroll || !innerRef.current) {
      if (scrollParentRef.current) {
        containerRef(null)
        scrollParentRef.current = null
      }
      return
    }

    // Already found — skip the DOM walk
    if (scrollParentRef.current) return

    const scrollable = findScrollableParent(
      innerRef.current,
      CHAT_CONTAINER_TAG,
    )
    if (scrollable) {
      containerRef(scrollable)
      scrollParentRef.current = scrollable
    }
  }, [autoScroll, content, containerRef])

  useEffect(() => {
    return () => {
      if (scrollParentRef.current) {
        containerRef(null)
        scrollParentRef.current = null
      }
    }
  }, [containerRef])

  const appendContent = useCallback((chunk: string) => {
    setContent((prev) => prev + chunk)
  }, [])

  const replaceContent = useCallback((newContent: string) => {
    setContent(newContent)
  }, [])

  const api = useMemo(
    () => ({
      appendContent,
      replaceContent,
      setStreaming,
      setContentType,
    }),
    [appendContent, replaceContent],
  )

  useEffect(() => {
    onApiReady?.(api)
  }, [api, onApiReady])

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
