import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  type ComponentType,
} from "react"
import { toHtml } from "hast-util-to-html"
import type { Element } from "hast"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { useAutoScroll, findScrollableParent } from "../markdown/useAutoScroll"
import type { ContentType } from "../transport/types"

const CHAT_CONTAINER_TAG = "shiny-chat-container"

export type ContentSegment = {
  text: string
  trusted: boolean
}

const EscapedIsland = (({ node }: { node?: Element }) => (
  <>{node ? toHtml(node) : ""}</>
)) as ComponentType<unknown>

// This is the only island escape on untrusted `contentType="html"` segments;
// the processor-level disguise/escape pair applies only to Markdown.
const escapedIslandComponents: Record<string, ComponentType<unknown>> = {
  "shiny-chat-raw-html": EscapedIsland,
  "shinychat-raw-html": EscapedIsland,
}

export interface MarkdownStreamProps {
  initialContent?: string
  initialSegments?: ContentSegment[]
  initialContentType?: ContentType
  initialStreaming?: boolean
  initialTrusted?: boolean
  autoScroll?: boolean
  onApiReady?: (api: MarkdownStreamApi) => void
}

export type MarkdownStreamApi = {
  appendContent: (
    chunk: string,
    trusted?: boolean,
    startSegment?: boolean,
  ) => void
  replaceContent: (content: string, trusted?: boolean) => void
  setStreaming: (streaming: boolean) => void
  setContentType: (contentType: ContentType) => void
}

/** Standalone component for the <shiny-markdown-stream> custom element. */
export function MarkdownStream({
  initialContent = "",
  initialSegments,
  initialContentType = "markdown",
  initialStreaming = false,
  initialTrusted = false,
  autoScroll = false,
  onApiReady,
}: MarkdownStreamProps) {
  const [segments, setSegments] = useState<ContentSegment[]>(
    initialSegments ?? [{ text: initialContent, trusted: initialTrusted }],
  )
  const [contentType, setContentType] =
    useState<ContentType>(initialContentType)
  const [streaming, setStreaming] = useState(initialStreaming)
  const innerRef = useRef<HTMLDivElement>(null)
  const scrollParentRef = useRef<HTMLElement | null>(null)

  // Auto-scroll: the hook gives us a callback ref for the scrollable container.
  // In standalone mode we don't own the scrollable ancestor, so we do a one-time
  // DOM walk on mount and wire the callback ref to the found element.
  const { containerRef, scrollToBottom, repinIfAtBottom } = useAutoScroll({
    streaming: autoScroll && streaming,
    contentDependency: segments,
  })

  useLayoutEffect(() => {
    if (!autoScroll || !innerRef.current) {
      if (scrollParentRef.current) {
        containerRef(null)
        scrollParentRef.current = null
      }
      return
    }

    const scrollable = findScrollableParent(
      innerRef.current,
      CHAT_CONTAINER_TAG,
    )
    if (scrollable !== scrollParentRef.current) {
      containerRef(scrollable)
      scrollParentRef.current = scrollable
    }
  }, [autoScroll, segments, containerRef])

  useEffect(() => {
    return () => {
      if (scrollParentRef.current) {
        containerRef(null)
        scrollParentRef.current = null
      }
    }
  }, [containerRef])

  useEffect(() => {
    if (streaming && autoScroll) {
      scrollToBottom()
    }
  }, [streaming, autoScroll, scrollToBottom])

  const appendContent = useCallback(
    (chunk: string, trusted = false, startSegment = false) => {
      // Settle pinnedness here, before React grows the DOM: at this point
      // "at the bottom" is unambiguous. Leaving it to the scroll handler alone
      // loses the race whenever the scroll event lands after the growth.
      repinIfAtBottom()
      setSegments((prev) => {
        const last = prev[prev.length - 1]
        if (!startSegment && last && last.trusted === trusted) {
          return [...prev.slice(0, -1), { ...last, text: last.text + chunk }]
        }
        return [...prev, { text: chunk, trusted }]
      })
    },
    [repinIfAtBottom],
  )

  const replaceContent = useCallback((newContent: string, trusted = false) => {
    setSegments([{ text: newContent, trusted }])
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
      {segments.map((segment, index) => (
        <MarkdownContent
          key={index}
          content={segment.text}
          contentType={contentType}
          streaming={streaming && index === segments.length - 1}
          allowRawHtmlIslands={segment.trusted}
          tagToComponentMap={
            segment.trusted ? undefined : escapedIslandComponents
          }
        />
      ))}
    </div>
  )
}
