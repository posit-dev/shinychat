import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  type ComponentType,
} from "react"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { EscapedIsland } from "../markdown/EscapedIsland"
import { useAutoScroll, findScrollableParent } from "../markdown/useAutoScroll"
import { HtmlBlockContent } from "../chat/HtmlBlockContent"
import type { HtmlBlock } from "../chat/html-block-model"
import type { ContentType } from "../transport/types"

const CHAT_CONTAINER_TAG = "shiny-chat-container"

export type ContentSegment = {
  text: string
  trusted: boolean
}

/**
 * One item of stream state: a string segment (with trust provenance) or a
 * structured `html_block` island. Blocks are hard structural boundaries —
 * adjacent same-trust string segments merge, but a block never merges with
 * anything.
 */
export type StreamSegment = ContentSegment | HtmlBlock

/** Structural discrimination: string segments carry `text`; blocks a `type`. */
function isBlockSegment(segment: StreamSegment): segment is HtmlBlock {
  return "type" in segment
}

// This is the only island escape on untrusted `contentType="html"` segments;
// the processor-level disguise/escape pair applies only to Markdown.
const escapedIslandComponents: Record<string, ComponentType<unknown>> = {
  "shiny-chat-raw-html": EscapedIsland,
  "shinychat-raw-html": EscapedIsland,
}

export interface MarkdownStreamProps {
  initialContent?: string
  initialSegments?: StreamSegment[]
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
  /** Append one complete structured `html_block` island. */
  appendBlock: (block: HtmlBlock) => void
  replaceContent: (content: string, trusted?: boolean) => void
  /**
   * Uniform replace for a block-carrying message (kata#0r4g): wipe ALL
   * segments and blocks, then append the block.
   */
  replaceWithBlock: (block: HtmlBlock) => void
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
  const [segments, setSegments] = useState<StreamSegment[]>(
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
        // Blocks are hard boundaries: text only merges into a trailing
        // string segment of equal trust, never into (or across) a block.
        if (
          !startSegment &&
          last &&
          !isBlockSegment(last) &&
          last.trusted === trusted
        ) {
          return [...prev.slice(0, -1), { ...last, text: last.text + chunk }]
        }
        return [...prev, { text: chunk, trusted }]
      })
    },
    [repinIfAtBottom],
  )

  const appendBlock = useCallback(
    (block: HtmlBlock) => {
      // Same pinnedness settle as appendContent: a block grows the DOM too.
      repinIfAtBottom()
      setSegments((prev) => [...prev, block])
    },
    [repinIfAtBottom],
  )

  const replaceContent = useCallback((newContent: string, trusted = false) => {
    setSegments([{ text: newContent, trusted }])
  }, [])

  const replaceWithBlock = useCallback(
    (block: HtmlBlock) => {
      repinIfAtBottom()
      setSegments([block])
    },
    [repinIfAtBottom],
  )

  const api = useMemo(
    () => ({
      appendContent,
      appendBlock,
      replaceContent,
      replaceWithBlock,
      setStreaming,
      setContentType,
    }),
    [appendContent, appendBlock, replaceContent, replaceWithBlock],
  )

  useEffect(() => {
    onApiReady?.(api)
  }, [api, onApiReady])

  return (
    <div ref={innerRef}>
      {segments.map((segment, index) =>
        isBlockSegment(segment) ? (
          // A structured raw-HTML island renders through the same sink Chat
          // uses — no markdown-pipeline round-trip. The streaming dot lives
          // in the markdown pipeline, so a trailing block shows no dot; it
          // resumes with the next string segment.
          <HtmlBlockContent
            key={index}
            content={segment.content}
            htmlDeps={segment.htmlDeps}
          />
        ) : (
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
        ),
      )}
    </div>
  )
}
