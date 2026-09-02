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
import { HtmlBlockContent } from "../chat/HtmlBlockContent"
import type { HtmlBlock } from "../chat/html-block-model"
import { WebActivity } from "../chat/WebActivity"
import {
  appendWebActivityBlock,
  applyWebBlock,
  type WebActivityBlock,
  type WebActivityWireBlock,
} from "../chat/web-activity-model"
import {
  chatTagToComponentMap,
  untrustedChatTagToComponentMap,
} from "../chat/chatTagToComponentMap"
import type { ContentType } from "../transport/types"

const CHAT_CONTAINER_TAG = "shiny-chat-container"

export type ContentSegment = {
  text: string
  trusted: boolean
}

/**
 * One item of stream state: a string segment, a structured `html_block`
 * island, or a grouped web-activity block. Blocks are hard structural
 * boundaries — adjacent same-trust string segments merge, but a block
 * never merges with anything.
 */
export type StreamSegment = ContentSegment | HtmlBlock | WebActivityBlock

/** A validated block accepted by the stream API: an `html_block` island or a web_* wire block. */
export type StreamBlock = HtmlBlock | WebActivityWireBlock

/** Structural discrimination: string segments carry `text`; blocks a `type`. */
function isBlockSegment(
  segment: StreamSegment,
): segment is HtmlBlock | WebActivityBlock {
  return "type" in segment
}

/** Whitespace-separator check for appendWebActivityBlock (mirrors rehypeGroupWebActivity). */
export function isWhitespaceTextSegment(segment: StreamSegment): boolean {
  return !isBlockSegment(segment) && segment.text.trim() === ""
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
  /** Append one complete structured block (html_block or web_*). */
  appendBlock: (block: StreamBlock) => void
  replaceContent: (content: string, trusted?: boolean) => void
  /** Uniform replace: wipe all segments and blocks, then append the block. */
  replaceWithBlock: (block: StreamBlock) => void
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
  // Count block mounts so scroll-parent discovery and auto-scroll re-run
  // when a deps-gated block finally mounts (segments doesn't change then).
  const [blockMounts, setBlockMounts] = useState(0)
  const handleBlockMounted = useCallback(() => {
    setBlockMounts((n) => n + 1)
  }, [])

  // Auto-scroll: the hook gives us a callback ref for the scrollable container.
  // In standalone mode we don't own the scrollable ancestor, so we do a one-time
  // DOM walk on mount and wire the callback ref to the found element.
  const scrollContentDependency = useMemo(
    () => [segments, blockMounts],
    [segments, blockMounts],
  )
  const { containerRef, scrollToBottom, repinIfAtBottom } = useAutoScroll({
    streaming: autoScroll && streaming,
    contentDependency: scrollContentDependency,
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
  }, [autoScroll, segments, blockMounts, containerRef])

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
        // string segment of equal trust.
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
    (block: StreamBlock) => {
      repinIfAtBottom()
      setSegments((prev) =>
        block.type === "html_block"
          ? [...prev, block]
          : appendWebActivityBlock(prev, block, isWhitespaceTextSegment),
      )
    },
    [repinIfAtBottom],
  )

  const replaceContent = useCallback((newContent: string, trusted = false) => {
    setSegments([{ text: newContent, trusted }])
  }, [])

  const replaceWithBlock = useCallback(
    (block: StreamBlock) => {
      repinIfAtBottom()
      setSegments(
        block.type === "html_block"
          ? [block]
          : appendWebActivityBlock([], block, isWhitespaceTextSegment),
      )
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
          segment.type === "web_activity" ? (
            <WebActivity key={index} items={segment.items} />
          ) : (
            <HtmlBlockContent
              key={index}
              content={segment.content}
              htmlDeps={segment.htmlDeps}
              onMounted={handleBlockMounted}
            />
          )
        ) : (
          <MarkdownContent
            key={index}
            content={segment.text}
            contentType={contentType}
            streaming={streaming && index === segments.length - 1}
            tagToComponentMap={
              segment.trusted
                ? chatTagToComponentMap
                : untrustedChatTagToComponentMap
            }
          />
        ),
      )}
    </div>
  )
}
