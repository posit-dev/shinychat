import type {
  ContentType,
  StructuredBlock,
  ToolResultBlock,
} from "../transport/types"
import type { ChatMessageData, MessageBlock } from "./state"
import { uuid } from "../utils/uuid"
import {
  containsToolMarker,
  isRoutableContentType,
  parseToolEvents,
  type ToolEvent,
  type ToolResultOpenStyle,
} from "./tool-protocol"

/** How a loop's tool calls are aggregated in the condensed view. */
export type ToolGrouping = "none" | "tool" | "all"

/**
 * One tool call — a request and/or its matching result, parsed out of
 * assistant content by the content router. It carries both condensed-view
 * metadata and the payload needed to render the leaf card.
 */
export interface ToolCallItem {
  /**
   * The server-emitted request identifier, which pairs a request with its
   * result and keys transcript-wide request suppression. It is empty when
   * omitted.
   */
  requestId: string
  /** Loop-local unique id: the request identifier, or a synthetic id when absent. */
  localId: string
  toolName: string
  status: "running" | "success" | "error"
  /** Dynamic (result) title. */
  title?: string
  /** Static (definition) title from the request's tool annotation. */
  definitionTitle?: string
  /** Dynamic (result) icon. */
  icon?: string
  /** Static (definition) icon from the request's tool annotation. */
  definitionIcon?: string
  label?: string
  valuePreview?: string
  intent?: string
  /** Per-tool grouping override from the element's `grouping` attribute. */
  grouping?: ToolGrouping
  // Tier-3 leaf payload
  value?: string
  valueType?: string
  requestCall?: string
  showRequest?: boolean
  fullScreen?: boolean
  openStyle?: ToolResultOpenStyle
  expanded?: boolean
  /**
   * Internal wire provenance: the server wrapped an author's custom UI in a
   * real result element. Phase 3 decides how this fact affects placement.
   */
  customDisplay?: boolean
  /**
   * Wire provenance: this call arrived as a structured wire block (e.g.
   * `tool_result`), not markup parsed out of a loop's `content` slice. A
   * structured call has no raw content to re-parse, so rerouteMessage
   * re-groups it from the stored call data — even when a merge has given its
   * loop a nonempty `content` (mixed markup+structured loop).
   */
  structured?: true
  /**
   * Character offset of the result element within its source content block.
   * Used by the current presentation layer to order migrated payloads.
   */
  resolveIndex?: number
  /** Source content block index, paired with resolveIndex for ordering. */
  resolveBlock?: number
  footer?: string
  /** Raw arguments JSON from the request element. */
  arguments?: string
}

/** One tool's contribution to a group's header. */
export interface ToolCallSegment {
  toolName: string
  title?: string
  count: number
  settled: boolean
}

/** Block-model data for an aggregated set of calls. */
export interface ToolCallGroup {
  /** Grouping key (per-call, per-tool, or loop-wide). */
  key: string
  toolName: string
  title?: string
  titleSettled: boolean
  icon?: string
  count: number
  segments: ToolCallSegment[]
  calls: ToolCallItem[]
}

/** A run of adjacent tool calls (one agentic loop). */
export interface ToolLoopBlock {
  type: "tool_loop"
  content: string
  contentType: ContentType
  grouping: ToolGrouping
  groups: ToolCallGroup[]
}

export interface ToolGroupIdentity {
  title?: string
  titleSettled: boolean
  icon?: string
  count: number
  segments: ToolCallSegment[]
}

function applyEvent(
  item: ToolCallItem,
  event: ToolEvent,
  sourceBlock: number,
): void {
  if (event.toolName) item.toolName = event.toolName
  if (event.grouping !== undefined) item.grouping = event.grouping
  if (event.intent !== undefined) item.intent = event.intent

  if (event.kind === "request") {
    if (event.definitionTitle !== undefined) {
      item.definitionTitle = event.definitionTitle
    }
    if (event.definitionIcon !== undefined) {
      item.definitionIcon = event.definitionIcon
    }
    if (event.arguments !== undefined) item.arguments = event.arguments
    return
  }

  if (event.title !== undefined) item.title = event.title
  if (event.icon !== undefined) item.icon = event.icon
  item.status = event.status
  if (event.label !== undefined) item.label = event.label
  if (event.valuePreview !== undefined) item.valuePreview = event.valuePreview
  if (event.value !== undefined) item.value = event.value
  if (event.valueType !== undefined) item.valueType = event.valueType
  if (event.requestCall !== undefined) item.requestCall = event.requestCall
  if (event.footer !== undefined) item.footer = event.footer
  item.showRequest = event.showRequest
  item.fullScreen = event.fullScreen
  item.openStyle = event.openStyle
  item.expanded = event.expanded
  item.customDisplay = event.customDisplay
  item.resolveIndex = event.start
  item.resolveBlock = sourceBlock
}

/**
 * Pair normalized protocol events into lifecycle calls. Events without a
 * request identifier receive stable loop-local identities; those ids
 * intentionally never enter transcript supersession.
 */
export function pairToolEvents(
  events: ToolEvent[],
  anonScope: string,
  sourceBlock: number,
): ToolCallItem[] {
  const order: string[] = []
  const byId = new Map<string, ToolCallItem>()
  events.forEach((event, i) => {
    const requestId = event.requestId
    const id = requestId || `__anon-${anonScope}-${i}`
    let item = byId.get(id)
    if (!item) {
      item = {
        requestId,
        localId: id,
        toolName: event.toolName,
        status: "running",
      }
      byId.set(id, item)
      order.push(id)
    }
    applyEvent(item, event, sourceBlock)
  })
  return order.map((id) => byId.get(id)!)
}

// An aggregated set keeps the static definition title so the header stays
// stable across calls' differing dynamic titles. A lone call shows its most
// specific dynamic title instead.
function resolveTitle(calls: ToolCallItem[]): string | undefined {
  const firstDone = calls.find((c) => c.status !== "running")
  const definitionTitle = calls.find(
    (c) => c.definitionTitle !== undefined,
  )?.definitionTitle
  const resultTitle =
    firstDone?.title ?? calls.find((c) => c.title !== undefined)?.title
  return calls.length > 1
    ? (definitionTitle ?? resultTitle)
    : (resultTitle ?? definitionTitle)
}

// An aggregated set keeps only a shared definition icon. A lone call can show
// its result-specific icon.
function resolveIcon(calls: ToolCallItem[]): string | undefined {
  const definitionIcon = calls.find(
    (c) => c.definitionIcon !== undefined,
  )?.definitionIcon
  if (calls.length === 1) return calls[0]!.icon ?? definitionIcon
  return definitionIcon
}

function buildSegments(calls: ToolCallItem[]): ToolCallSegment[] {
  const order: string[] = []
  const byTool = new Map<string, ToolCallItem[]>()
  for (const c of calls) {
    let bucket = byTool.get(c.toolName)
    if (!bucket) {
      bucket = []
      byTool.set(c.toolName, bucket)
      order.push(c.toolName)
    }
    bucket.push(c)
  }
  return order.map((toolName) => {
    const tcalls = byTool.get(toolName)!
    return {
      toolName,
      title: resolveTitle(tcalls),
      count: tcalls.length,
      settled: tcalls.some((c) => c.status !== "running"),
    }
  })
}

/** Derive a group's identity from the calls currently represented by it. */
export function deriveToolGroupIdentity(
  calls: ToolCallItem[],
): ToolGroupIdentity {
  const firstDone = calls.find((c) => c.status !== "running")
  return {
    title: resolveTitle(calls),
    titleSettled: firstDone !== undefined,
    icon: resolveIcon(calls),
    count: calls.length,
    segments: buildSegments(calls),
  }
}

// Group a loop's calls per the chat-level grouping, honoring per-tool
// overrides. none -> one group per call; tool -> by tool name; all -> one loop.
function groupCalls(
  calls: ToolCallItem[],
  chatGrouping: ToolGrouping,
): ToolCallGroup[] {
  const override = new Map<string, ToolGrouping>()
  // Chat-level none turns grouping off entirely. An annotation cannot opt back
  // into grouping after the app has switched grouping off.
  if (chatGrouping !== "none") {
    for (const c of calls) {
      if (c.grouping && !override.has(c.toolName)) {
        override.set(c.toolName, c.grouping)
      }
    }
  }

  const keyOrder: string[] = []
  const byKey = new Map<string, ToolCallItem[]>()
  calls.forEach((c) => {
    const mode = override.get(c.toolName) ?? chatGrouping
    const key =
      mode === "none"
        ? `none:${c.localId}`
        : mode === "all"
          ? "all"
          : `tool:${c.toolName}`
    let bucket = byKey.get(key)
    if (!bucket) {
      bucket = []
      byKey.set(key, bucket)
      keyOrder.push(key)
    }
    bucket.push(c)
  })

  return keyOrder.map((key) => {
    const gcalls = byKey.get(key)!
    const identity = deriveToolGroupIdentity(gcalls)
    return {
      key,
      toolName: gcalls[0]!.toolName,
      title: identity.title,
      titleSettled: identity.titleSettled,
      icon: identity.icon,
      count: identity.count,
      calls: gcalls,
      segments: identity.segments,
    }
  })
}

function makeToolLoopBlock(
  events: ToolEvent[],
  content: string,
  contentType: ContentType,
  grouping: ToolGrouping,
  anonScope: string,
  sourceBlock: number,
): ToolLoopBlock {
  const calls = pairToolEvents(events, anonScope, sourceBlock)
  return {
    type: "tool_loop",
    content,
    contentType,
    grouping,
    groups: groupCalls(calls, grouping),
  }
}

/**
 * Pure content router: split content blocks around runs of tool elements,
 * emitting ToolLoopBlocks. It is replayable for history restore and rerenders.
 */
export function routeToolBlocks(
  blocks: MessageBlock[],
  grouping: ToolGrouping,
  // "system" is reachable from the server even though the client message
  // model only names "user" | "assistant".
  role: string,
  shieldOpenFence = false,
): MessageBlock[] {
  // Tool elements are server-authored. In a user message, routing would bypass
  // MarkdownContent's escaping and sanitization and allow typed spoofing.
  if (role === "user") return blocks

  const out: MessageBlock[] = []

  blocks.forEach((block, blockIndex) => {
    if (
      block.type !== "content" ||
      !isRoutableContentType(block.contentType) ||
      !containsToolMarker(block.content)
    ) {
      out.push(block)
      return
    }
    const events = parseToolEvents(
      block.content,
      block.contentType,
      shieldOpenFence,
    )
    if (events.length === 0) {
      out.push(block)
      return
    }

    const contentType = block.contentType
    let cursor = 0
    let loopStart = -1
    let loopEvents: ToolEvent[] = []

    const flush = () => {
      if (loopEvents.length === 0) return
      out.push(
        makeToolLoopBlock(
          loopEvents,
          block.content.slice(loopStart, cursor),
          contentType,
          grouping,
          `${blockIndex}:${loopStart}`,
          blockIndex,
        ),
      )
      loopEvents = []
      loopStart = -1
    }

    for (const event of events) {
      const between = block.content.slice(cursor, event.start)
      if (between.trim() !== "") {
        flush()
        out.push({ type: "content", content: between, contentType })
      }
      if (loopEvents.length === 0) loopStart = event.start
      loopEvents.push(event)
      cursor = event.end
    }
    flush()

    const tail = block.content.slice(cursor)
    if (tail.trim() !== "") {
      out.push({ type: "content", content: tail, contentType })
    }
  })

  return mergeAdjacentLoops(out, grouping)
}

// Coalesce loops that are adjacent and share a content type, so grouping spans
// the whole run without changing the rendering type of either source block.
function mergeAdjacentLoops(
  blocks: MessageBlock[],
  grouping: ToolGrouping,
): MessageBlock[] {
  const out: MessageBlock[] = []
  for (const block of blocks) {
    const prev = out[out.length - 1]
    if (
      block.type === "tool_loop" &&
      prev?.type === "tool_loop" &&
      prev.contentType === block.contentType
    ) {
      const calls = [...prev.groups.flatMap((g) => g.calls)]
      const combinedContent = prev.content + block.content
      const combinedCalls = calls.concat(block.groups.flatMap((g) => g.calls))
      out[out.length - 1] = {
        type: "tool_loop",
        content: combinedContent,
        contentType: prev.contentType,
        grouping,
        groups: groupCalls(combinedCalls, grouping),
      }
    } else {
      out.push(block)
    }
  }
  return out
}

/**
 * Convert a structured `tool_result` wire block into a lifecycle call. The
 * envelope is server-authored, so its fields map directly onto the call — no
 * markup parsing, no attribute decoding, no entity decoding.
 */
export function toolResultBlockToCall(block: ToolResultBlock): ToolCallItem {
  const call: ToolCallItem = {
    requestId: block.request_id,
    // pairToolEvents' convention: the request id, or a synthetic loop-local
    // id that never enters transcript supersession.
    localId: block.request_id || `__anon-structured-${uuid()}`,
    toolName: block.tool_name,
    status: block.status,
    structured: true,
  }
  if (block.title !== undefined) call.title = block.title
  if (block.icon !== undefined) call.icon = block.icon
  if (block.label !== undefined) call.label = block.label
  if (block.value_preview !== undefined) call.valuePreview = block.value_preview
  if (block.intent !== undefined) call.intent = block.intent
  if (block.value !== undefined) call.value = block.value
  if (block.value_type !== undefined) call.valueType = block.value_type
  if (block.request_call !== undefined) call.requestCall = block.request_call
  if (block.show_request !== undefined) call.showRequest = block.show_request
  if (block.full_screen !== undefined) call.fullScreen = block.full_screen
  if (block.open_style !== undefined) call.openStyle = block.open_style
  if (block.expanded !== undefined) call.expanded = block.expanded
  if (block.custom_display !== undefined)
    call.customDisplay = block.custom_display
  if (block.footer !== undefined) call.footer = block.footer
  if (block.grouping !== undefined) call.grouping = block.grouping
  return call
}

/**
 * Convert a structured wire block into a render-ready ToolLoopBlock on
 * arrival (one block → one loop → one group → one call). Unknown block types
 * and unsupported versions are ignored with a warning — `version` is a
 * forward-compatibility marker, so a block this client predates must not
 * break the message around it.
 */
export function structuredBlockToLoop(
  block: StructuredBlock,
  grouping: ToolGrouping,
): ToolLoopBlock | null {
  // Read discriminator fields defensively: the wire is JSON and may carry
  // block types/versions this client doesn't know yet.
  const type = (block as { type?: unknown }).type
  if (type !== "tool_result") {
    console.warn(`Ignoring unknown structured block type: ${String(type)}`)
    return null
  }
  const version = (block as { version?: unknown }).version
  if (version !== 1) {
    console.warn(
      `Ignoring tool_result block with unsupported version: ${String(version)}`,
    )
    return null
  }
  const call = toolResultBlockToCall(block)
  return {
    type: "tool_loop",
    // A structured-derived loop has no raw content slice to re-parse; its
    // calls carry `structured: true` so rerouteMessage re-groups them from
    // the stored call data instead.
    content: "",
    contentType: "html",
    grouping,
    groups: groupCalls([call], grouping),
  }
}

/**
 * Append a structured-derived call to an existing tool loop, re-deriving the
 * groups from the combined call list (mirrors mergeAdjacentLoops).
 */
export function appendCallToToolLoop(
  loop: ToolLoopBlock,
  call: ToolCallItem,
  grouping: ToolGrouping,
): ToolLoopBlock {
  const calls = [...loop.groups.flatMap((g) => g.calls), call]
  return {
    type: "tool_loop",
    content: loop.content,
    contentType: loop.contentType,
    grouping,
    groups: groupCalls(calls, grouping),
  }
}

/**
 * Re-derive a loop's groups at a new grouping mode from the calls it already
 * holds. Used for structured-derived loops, which carry no raw content slice
 * to unwind and re-parse the way markup-derived loops do.
 */
export function regroupToolLoop(
  loop: ToolLoopBlock,
  grouping: ToolGrouping,
): ToolLoopBlock {
  const calls = loop.groups.flatMap((g) => g.calls)
  return { ...loop, grouping, groups: groupCalls(calls, grouping) }
}

/**
 * Build a structured-derived loop from calls split out of a mixed
 * markup+structured loop during rerouting: the calls keep their
 * `structured: true` provenance and the loop has no raw content slice.
 */
export function structuredCallsToLoop(
  calls: ToolCallItem[],
  grouping: ToolGrouping,
): ToolLoopBlock {
  return {
    type: "tool_loop",
    content: "",
    contentType: "html",
    grouping,
    groups: groupCalls(calls, grouping),
  }
}

/**
 * The request identifiers whose result has rendered somewhere in the
 * transcript.
 * This mirrors routeToolBlocks' role, content-type, and fence gates so a
 * result refused by the router cannot suppress a request row.
 */
export function supersededRequestIds(
  messages: ChatMessageData[],
  streamingMessage: ChatMessageData | null,
): Set<string> {
  const ids = new Set<string>()
  for (const msg of messages) collectResultIds(msg, ids)
  if (streamingMessage) collectResultIds(streamingMessage, ids)
  return ids
}

function collectResultIds(msg: ChatMessageData, into: Set<string>): void {
  if (msg.role === "user") return
  const shieldOpenFence = msg.streaming === true || msg.insideFence === true

  for (const block of msg.blocks) {
    if (block.type === "tool_loop") {
      // Keep migrated custom calls here: transcript suppression depends on the
      // lifecycle model, not on the presentation layer's visible subset.
      for (const group of block.groups) {
        for (const call of group.calls) {
          if (call.status !== "running" && call.requestId) {
            into.add(call.requestId)
          }
        }
      }
      continue
    }
    if (
      block.type !== "content" ||
      !isRoutableContentType(block.contentType) ||
      !containsToolMarker(block.content)
    ) {
      continue
    }
    for (const event of parseToolEvents(
      block.content,
      block.contentType,
      shieldOpenFence,
    )) {
      if (event.kind === "result" && event.requestId) {
        into.add(event.requestId)
      }
    }
  }
}
