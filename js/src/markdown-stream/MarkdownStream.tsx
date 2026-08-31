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
import { WebActivity } from "../chat/WebActivity"
import {
  appendWebActivityBlock,
  applyWebBlock,
  type WebActivityBlock,
  type WebActivityWireBlock,
} from "../chat/web-activity-model"
import { chatTagToComponentMap } from "../chat/chatTagToComponentMap"
import { UntrustedAsideGroup } from "../chat/AsideGroup"
import type { ContentType } from "../transport/types"

const CHAT_CONTAINER_TAG = "shiny-chat-container"

export type ContentSegment = {
  text: string
  trusted: boolean
}

/**
 * One item of stream state: a string segment (with trust provenance), a
 * structured `html_block` island, or a grouped web-activity block. Blocks
 * are hard structural boundaries — adjacent same-trust string segments
 * merge, but a block never merges with anything (web_* wire blocks group
 * into the trailing activity on arrival, before they enter state).
 */
export type StreamSegment = ContentSegment | HtmlBlock | WebActivityBlock

/**
 * A validated block accepted by the stream API: a render-model `html_block`
 * island, or a validated web_* wire block. Web blocks stay in wire form
 * across the API boundary because the grouping machinery
 * (appendWebActivityBlock) consumes wire blocks.
 */
export type StreamBlock = HtmlBlock | WebActivityWireBlock

/** Structural discrimination: string segments carry `text`; blocks a `type`. */
function isBlockSegment(
  segment: StreamSegment,
): segment is HtmlBlock | WebActivityBlock {
  return "type" in segment
}

/**
 * MarkdownStream's whitespace-separator check for appendWebActivityBlock: a
 * whitespace-only string segment between web_* carriers is part of the run
 * (dropped on grouping), mirroring rehypeGroupWebActivity's tolerance of
 * whitespace text nodes.
 */
export function isWhitespaceTextSegment(segment: StreamSegment): boolean {
  return !isBlockSegment(segment) && segment.text.trim() === ""
}

// Trusted segments resolve the aside data carriers through
// chatTagToComponentMap (the same mappings Chat's trusted content gets).
// Untrusted segments get them too — asides are data carriers, not trust
// sinks (mirroring Chat's untrustedChatTagToComponentMap) — plus the
// raw-html island escape, the only island escape on untrusted
// `contentType="html"` segments (the processor-level disguise/escape pair
// applies only to Markdown). The aside-group resolver is the untrusted
// variant: the popover body reparse must keep these escapes, or a forged
// island inside an aside would reach RawHTML/innerHTML when the popover
// opens.
const untrustedStreamComponents: Record<string, ComponentType<unknown>> = {
  ...chatTagToComponentMap,
  "shiny-aside-group": UntrustedAsideGroup as ComponentType<unknown>,
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
  /**
   * Append one complete structured block: an `html_block` island lands as a
   * hard boundary; a web_* block groups into the trailing web activity per
   * appendWebActivityBlock's semantics.
   */
  appendBlock: (block: StreamBlock) => void
  replaceContent: (content: string, trusted?: boolean) => void
  /**
   * Uniform replace for a block-carrying message (kata#0r4g): wipe ALL
   * segments and blocks, then append the block.
   */
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
  // A deps-gated block renders nothing until its dependencies load; when it
  // finally mounts, `segments` doesn't change. Count block mounts so the
  // scroll-parent discovery and auto-scroll below re-run for that growth.
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
    (block: StreamBlock) => {
      // Same pinnedness settle as appendContent: a block grows the DOM too.
      repinIfAtBottom()
      setSegments((prev) =>
        block.type === "html_block"
          ? [...prev, block]
          : // A web_* block joins the trailing web activity when one is
            // reachable (tolerating a whitespace-only text segment between
            // carriers) — the shared grouping/pairing semantics.
            appendWebActivityBlock(prev, block, isWhitespaceTextSegment),
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
      // Uniform replace: wipe everything, then the block lands on an emptied
      // stream (a web_* block starts a fresh activity).
      setSegments(
        block.type === "html_block" ? [block] : [applyWebBlock(null, block)],
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
            // A grouped web-activity block renders through the same
            // component Chat uses — no markdown-pipeline round-trip.
            <WebActivity key={index} items={segment.items} />
          ) : (
            // A structured raw-HTML island renders through the same sink Chat
            // uses — no markdown-pipeline round-trip. The streaming dot lives
            // in the markdown pipeline, so a trailing block shows no dot; it
            // resumes with the next string segment.
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
            allowRawHtmlIslands={segment.trusted}
            tagToComponentMap={
              segment.trusted
                ? chatTagToComponentMap
                : untrustedStreamComponents
            }
          />
        ),
      )}
    </div>
  )
}
