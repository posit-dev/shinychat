import type {
  ContentType,
  StructuredBlock,
  ToolRequestBlock,
  ToolResultBlock,
} from "../transport/types"
import type { ChatMessageData, MessageBlock } from "./state"
import { uuid } from "../utils/uuid"
import type { ToolResultOpenStyle } from "./tool-protocol"

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

/**
 * Convert a structured `tool_request` wire block into a lifecycle call. The
 * envelope is server-authored, so its fields map directly onto the call — no
 * markup parsing, no attribute decoding, no entity decoding. An unpaired
 * request is a running call (convention for new request
 * ids); the matching `tool_result` block settles it, and transcript-wide
 * supersession then hides the request row.
 */
export function toolRequestBlockToCall(block: ToolRequestBlock): ToolCallItem {
  const call: ToolCallItem = {
    requestId: block.request_id,
    // convention: the request id, or a synthetic loop-local
    // id that never enters transcript supersession.
    localId: block.request_id || `__anon-structured-${uuid()}`,
    toolName: block.tool_name,
    // "running" is derived, never a wire value: a request with no result yet.
    status: "running",
    structured: true,
  }
  // The request carries the tool *definition's* title/icon (the markup path's
  // definitionTitle/definitionIcon); the result's own title/icon settle over
  // them when it arrives.
  if (block.title !== undefined) call.definitionTitle = block.title
  if (block.icon !== undefined) call.definitionIcon = block.icon
  if (block.intent !== undefined) call.intent = block.intent
  if (block.arguments !== undefined) call.arguments = block.arguments
  if (block.grouping !== undefined) call.grouping = block.grouping
  return call
}

/**
 * Convert a structured `tool_result` wire block into a lifecycle call. The
 * envelope is server-authored, so its fields map directly onto the call — no
 * markup parsing, no attribute decoding, no entity decoding.
 */
export function toolResultBlockToCall(block: ToolResultBlock): ToolCallItem {
  const call: ToolCallItem = {
    requestId: block.request_id,
    // convention: the request id, or a synthetic loop-local
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
  if (type !== "tool_request" && type !== "tool_result") {
    console.warn(`Ignoring unknown structured block type: ${String(type)}`)
    return null
  }
  const version = (block as { version?: unknown }).version
  if (version !== 1) {
    console.warn(
      `Ignoring ${type} block with unsupported version: ${String(version)}`,
    )
    return null
  }
  const call =
    type === "tool_request"
      ? toolRequestBlockToCall(block as ToolRequestBlock)
      : toolResultBlockToCall(block as ToolResultBlock)
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
 * groups from the combined call list.
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
 * Append a one-call tool loop (from a structured block) to a message's block
 * list, merging into an adjacent trailing tool loop when one is reachable —
 * tolerating a whitespace-only content block between carriers, exactly as
 * `appendWebActivityBlock` tolerates whitespace between web_* blocks (the
 * whitespace is dropped; any other block ends the run and starts a new loop).
 */
export function appendToolLoopBlock(
  blocks: MessageBlock[],
  loop: ToolLoopBlock,
  grouping: ToolGrouping,
): MessageBlock[] {
  const out = [...blocks]
  let tail = out[out.length - 1]
  if (tail?.type === "content" && tail.content.trim() === "") {
    const prev = out[out.length - 2]
    if (prev?.type === "tool_loop") {
      // The whitespace-only separator is part of the run; drop it.
      out.pop()
      tail = prev
    }
  }
  const call = loop.groups[0]?.calls[0]
  if (tail?.type === "tool_loop" && call) {
    out[out.length - 1] = appendCallToToolLoop(tail, call, grouping)
  } else {
    out.push(loop)
  }
  return out
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
 * The request identifiers whose result has rendered somewhere in the
 * transcript.
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

  for (const block of msg.blocks) {
    if (block.type !== "tool_loop") continue
    // Keep migrated custom calls here: transcript suppression depends on the
    // lifecycle model, not on the presentation layer's visible subset.
    for (const group of block.groups) {
      for (const call of group.calls) {
        if (call.status !== "running" && call.requestId) {
          into.add(call.requestId)
        }
      }
    }
  }
}
