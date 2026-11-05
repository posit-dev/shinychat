import type {
  ContentType,
  StructuredBlock,
  ToolRequestBlock,
  ToolResultBlock,
} from "../transport/types"
import type { ChatMessageData, RenderBlock } from "./state"
import { uuid } from "../utils/uuid"

/** How a loop's tool calls are aggregated in the condensed view. */
export type ToolGrouping = "none" | "tool" | "all"

/** Display style for a tool result's expandable region. */
export type ToolResultOpenStyle = "minimal" | "framed"

/** One tool call, a request and/or its matching result. */
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
  /** Internal: the server wrapped an author's custom UI in a real result element. */
  customDisplay?: boolean
  /** True when this call arrived as a structured wire block, not parsed from markup. */
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
// stable across calls' differing dynamic titles. Without one, it takes a
// result title only when every call shares it — one call's title must not
// stand for the others'. A lone call shows its most specific dynamic title
// instead.
function resolveTitle(calls: ToolCallItem[]): string | undefined {
  const firstDone = calls.find((c) => c.status !== "running")
  const definitionTitle = calls.find(
    (c) => c.definitionTitle !== undefined,
  )?.definitionTitle
  const resultTitle =
    firstDone?.title ?? calls.find((c) => c.title !== undefined)?.title
  if (calls.length === 1) return resultTitle ?? definitionTitle
  if (definitionTitle !== undefined) return definitionTitle
  const titles = new Set(calls.map((c) => c.title))
  return titles.size === 1 ? [...titles][0] : undefined
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

/** Convert a structured `tool_request` wire block into a lifecycle call. */
export function toolRequestBlockToCall(block: ToolRequestBlock): ToolCallItem {
  const call: ToolCallItem = {
    requestId: block.request_id,
    localId: block.request_id || `__anon-structured-${uuid()}`,
    toolName: block.tool_name,
    status: "running",
    structured: true,
  }
  if (block.title !== undefined) call.definitionTitle = block.title
  if (block.icon !== undefined) call.definitionIcon = block.icon
  if (block.intent !== undefined) call.intent = block.intent
  if (block.arguments !== undefined) call.arguments = block.arguments
  if (block.grouping !== undefined) call.grouping = block.grouping
  return call
}

/** Convert a structured `tool_result` wire block into a lifecycle call. */
export function toolResultBlockToCall(block: ToolResultBlock): ToolCallItem {
  const call: ToolCallItem = {
    requestId: block.request_id,
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
  if (block.request_call !== undefined) {
    // Defensive: some servers have sent the call as an array of wrapped
    // lines. The renderer expects a single string.
    const rc = block.request_call
    call.requestCall = Array.isArray(rc)
      ? rc.join("\n")
      : typeof rc === "string"
        ? rc
        : String(rc)
  }
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

/** Convert a structured wire block into a render-ready ToolLoopBlock (one block → one loop → one call). */
export function structuredBlockToLoop(
  block: StructuredBlock,
  grouping: ToolGrouping,
): ToolLoopBlock | null {
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
  const { request_id, tool_name } = block as {
    request_id?: unknown
    tool_name?: unknown
  }
  if (typeof request_id !== "string" || typeof tool_name !== "string") {
    console.warn(
      `Ignoring malformed ${type} block: request_id and tool_name must be strings`,
    )
    return null
  }
  if (
    type === "tool_result" &&
    (block as { status?: unknown }).status !== "success" &&
    (block as { status?: unknown }).status !== "error"
  ) {
    console.warn(
      `Ignoring malformed tool_result block: status must be "success" or "error"`,
    )
    return null
  }
  const call =
    type === "tool_request"
      ? toolRequestBlockToCall(block as ToolRequestBlock)
      : toolResultBlockToCall(block as ToolResultBlock)
  return {
    type: "tool_loop",
    content: "",
    contentType: "html",
    grouping,
    groups: groupCalls([call], grouping),
  }
}

/** Append a call to an existing tool loop, re-deriving the groups. */
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
 * Append a one-call tool loop to a message's block list, merging into an
 * adjacent trailing tool loop. Tolerates a whitespace-only content block
 * between carriers.
 */
export function appendToolLoopBlock(
  blocks: RenderBlock[],
  loop: ToolLoopBlock,
  grouping: ToolGrouping,
): RenderBlock[] {
  const out = [...blocks]
  let tail = out[out.length - 1]
  if (tail?.type === "content" && tail.content.trim() === "") {
    const prev = out[out.length - 2]
    if (prev?.type === "tool_loop") {
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

/** Re-derive a loop's groups at a new grouping mode. */
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

/**
 * The definition identity a running request supplied for its call.
 */
export interface RequestDefinition {
  title?: string
  icon?: string
}

/**
 * Definition identity (title, icon) keyed by the request that supplied it.
 *
 * Request and result blocks remain separate lifecycle calls so they can arrive
 * in different messages. A result carries one `title`: its display title, or
 * the definition title when the tool sets none (servers send
 * `display.title ?? annotations.title`). It cannot mark which one it is, so
 * once the superseded request is filtered out, this index is the only source
 * of the tool's shared title. The same holds for the icon.
 */
export function requestDefinitions(
  messages: ChatMessageData[],
  streamingMessage: ChatMessageData | null,
): Map<string, RequestDefinition> {
  const definitions = new Map<string, RequestDefinition>()
  for (const msg of messages) collectRequestDefinitions(msg, definitions)
  if (streamingMessage) collectRequestDefinitions(streamingMessage, definitions)
  return definitions
}

function collectResultIds(msg: ChatMessageData, into: Set<string>): void {
  if (msg.role === "user") return

  for (const block of msg.blocks) {
    if (block.type !== "tool_loop") continue
    // Keep migrated custom calls: suppression is decided on the lifecycle
    // model, not the presentation layer's visible subset.
    for (const group of block.groups) {
      for (const call of group.calls) {
        if (call.status !== "running" && call.requestId) {
          into.add(call.requestId)
        }
      }
    }
  }
}

function collectRequestDefinitions(
  msg: ChatMessageData,
  into: Map<string, RequestDefinition>,
): void {
  if (msg.role === "user") return

  for (const block of msg.blocks) {
    if (block.type !== "tool_loop") continue
    for (const group of block.groups) {
      for (const call of group.calls) {
        if (call.status !== "running" || !call.requestId) continue
        if (
          call.definitionTitle === undefined &&
          call.definitionIcon === undefined
        ) {
          continue
        }
        if (into.has(call.requestId)) continue
        into.set(call.requestId, {
          title: call.definitionTitle,
          icon: call.definitionIcon,
        })
      }
    }
  }
}

/**
 * Restore a settled call's definition identity from its matching request.
 *
 * An explicit result title or icon remains intact (`??` never overwrites),
 * and keeping both fields lets the presentation layer distinguish
 * result-specific identity from the tool's stable identity. The icon is also
 * copied into the dynamic slot because `renderLeaf` passes `icon={item.icon}`
 * with no fallback; every title reader already falls back to
 * `definitionTitle`, so the title needs no copy.
 */
export function inheritRequestDefinition(
  call: ToolCallItem,
  definitions: ReadonlyMap<string, RequestDefinition>,
): ToolCallItem {
  if (call.status === "running" || !call.requestId) return call

  const definition = definitions.get(call.requestId)
  if (definition === undefined) return call

  const nextDefinitionTitle = call.definitionTitle ?? definition.title
  const nextDefinitionIcon = call.definitionIcon ?? definition.icon
  const nextIcon = call.icon ?? definition.icon
  if (
    nextDefinitionTitle === call.definitionTitle &&
    nextDefinitionIcon === call.definitionIcon &&
    nextIcon === call.icon
  ) {
    return call
  }

  return {
    ...call,
    definitionTitle: nextDefinitionTitle,
    definitionIcon: nextDefinitionIcon,
    icon: nextIcon,
  }
}
