import {
  deriveToolGroupIdentity,
  type ToolCallGroup,
  type ToolCallItem,
  type ToolCallSegment,
  type ToolGroupIdentity,
} from "./tool-model"

/** A tool-activity row after custom-display results have left it. */
export interface ToolGroupRowView {
  /** The lifecycle calls that remain in the activity row. */
  calls: ToolCallItem[]
  /** Header identity derived from exactly `calls`. */
  identity: ToolGroupIdentity
  /** The lone call rendered directly by a single-call row, when applicable. */
  single: ToolCallItem | null
  /** Whether a visible call is still running. */
  anyRunning: boolean
  /** The number of visible calls that failed. */
  failedCount: number
  /** Whether the row contains calls from more than one tool. */
  heterogeneous: boolean
  /** Whether a visible call requires the row to open so its detail is reachable. */
  hasExpandedCall: boolean
  /** Header titles keyed by tool name for Tier-2 call labels. */
  segmentTitles: ReadonlyMap<string, string | undefined>
}

/** A settled custom-display result rendered outside its activity row. */
export interface ToolStandalonePayloadView {
  /** Stable React key for this lifecycle call. */
  key: string
  /** The original lifecycle call, retained for consumers that need its metadata. */
  call: ToolCallItem
  /** The custom result payload to render without tool-card chrome. */
  value: string
  valueType: string
  showRequest: false
}

/** The presentation-only view of a lifecycle group. */
export interface ToolGroupPresentation {
  /** Null when all calls have migrated to standalone custom payloads. */
  row: ToolGroupRowView | null
  /** Settled custom-display payloads in transcript source order. */
  standalonePayloads: ToolStandalonePayloadView[]
}

/** A text label for a tool row, with optional code-font treatment. */
export interface ToolCallLabel {
  text: string
  code?: boolean
}

/** The semantic glyph a renderer should map to its own HTML or component. */
export type ToolGlyph =
  | { kind: "status"; status: ToolCallItem["status"] }
  | { kind: "icon"; icon: string }
  | { kind: "default" }

/** The content that changes as a tool-header segment crossfades. */
export interface ToolSegmentName {
  title?: string
  verb: string
  toolName: string
}

/** One visible header segment and the verb treatment it requires. */
export interface ToolHeaderSegmentView {
  segment: ToolCallSegment
  showVerb: boolean
}

/** The whole header segments that fit before the overflow summary. */
export interface ToolHeaderSegments {
  shown: ToolHeaderSegmentView[]
  overflowText: string | null
}

function isStandalonePayload(call: ToolCallItem): boolean {
  return call.customDisplay === true && call.status !== "running"
}

const ARG_PREVIEW_MAX = 40

/**
 * Produce a compact public-scalar-argument preview, or null when arguments
 * are absent, invalid, or do not contain a scalar value worth naming.
 */
export function toolArgumentPreview(argsJson?: string): string | null {
  if (!argsJson) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(argsJson)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object") return null

  const parts: string[] = []
  for (const [key, value] of Object.entries(
    parsed as Record<string, unknown>,
  )) {
    if (key.startsWith("_") || key.startsWith(".")) continue
    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean"
    ) {
      parts.push(`${key}: ${value}`)
      if (parts.length === 3) break
    }
  }

  if (parts.length === 0) return null
  const preview = parts.join(", ")
  return preview.length > ARG_PREVIEW_MAX
    ? `${preview.slice(0, ARG_PREVIEW_MAX - 1)}…`
    : preview
}

/**
 * Choose the per-call text that adds useful identity beyond the header.
 * Single-call rows already own their header, so they never repeat its title.
 */
export function toolCallLabel(
  call: ToolCallItem,
  segmentTitle: string | undefined,
  isSingle: boolean,
): ToolCallLabel | null {
  if (call.label) return { text: call.label }
  if (!isSingle && call.title && call.title !== segmentTitle) {
    return { text: call.title }
  }
  if (isSingle && segmentTitle) return null

  const argumentPreview = toolArgumentPreview(call.arguments)
  if (argumentPreview) return { text: argumentPreview, code: true }
  return isSingle ? null : { text: call.toolName, code: true }
}

// The servers emit the result icon as `display.icon ?? annotations.icon`, so
// it identifies this call only when it differs from the definition icon.
function resultSpecificIcon(call: ToolCallItem): string | undefined {
  if (!call.icon || call.icon === call.definitionIcon) return undefined
  return call.icon
}

/**
 * Select a Tier-2 glyph without coupling the policy to a particular icon
 * implementation. Running state wins over every identity signal.
 */
export function toolCallGlyph(
  call: ToolCallItem,
  heterogeneous: boolean,
): ToolGlyph {
  if (call.status === "running") return { kind: "status", status: "running" }

  const resultIcon = resultSpecificIcon(call)
  if (resultIcon) return { kind: "icon", icon: resultIcon }

  if (heterogeneous) {
    const icon = call.icon || call.definitionIcon
    if (icon) return { kind: "icon", icon }
  }

  return { kind: "status", status: call.status }
}

/** Select a Tier-1 glyph from already-projected row facts. */
export function toolGroupGlyph(row: ToolGroupRowView): ToolGlyph {
  if (row.anyRunning) return { kind: "status", status: "running" }
  if (row.heterogeneous) return { kind: "default" }
  return row.identity.icon
    ? { kind: "icon", icon: row.identity.icon }
    : { kind: "default" }
}

/** Build the title content that a segment can crossfade without its count. */
export function toolSegmentName(
  segment: ToolCallSegment,
  showVerb: boolean,
): ToolSegmentName {
  return {
    title: segment.title,
    verb: showVerb ? (segment.settled ? "Used " : "Using ") : "",
    toolName: segment.toolName,
  }
}

/** Key only the content that changes inside the crossfading title element. */
export function toolSegmentNameKey(name: ToolSegmentName): string {
  return name.title != null
    ? `title:${name.title}`
    : `tool:${name.verb}|${name.toolName}`
}

const SEGMENT_CHAR_BUDGET = 60
const MAX_SEGMENTS = 3

function toolSegmentTextLength(segment: ToolCallSegment): number {
  const text = segment.title
    ? segment.title.replace(/<[^>]*>/g, "")
    : `Used ${segment.toolName}`
  return text.length + (segment.count > 1 ? `×${segment.count}`.length : 0)
}

/**
 * Keep complete heterogeneous segments until the character budget or segment
 * cap is exhausted. The first segment always remains visible.
 */
export function toolHeaderSegments(
  segments: ToolCallSegment[],
): ToolHeaderSegments {
  const shown: ToolCallSegment[] = []
  let used = 0
  for (const segment of segments) {
    const cost =
      toolSegmentTextLength(segment) + (shown.length ? ", ".length : 0)
    const full =
      shown.length >= MAX_SEGMENTS || used + cost > SEGMENT_CHAR_BUDGET
    if (shown.length && full) break
    shown.push(segment)
    used += cost
  }
  const hidden = segments.length - shown.length
  const anyTitled = shown.some((segment) => segment.title !== undefined)
  return {
    shown: shown.map((segment, index) => ({
      segment,
      showVerb: anyTitled || index === 0,
    })),
    overflowText:
      hidden > 0
        ? `, and ${hidden} ${hidden === 1 ? "other" : "others"}`
        : null,
  }
}

/**
 * Convert immutable lifecycle data into the row and standalone payloads React
 * renders. Lifecycle calls deliberately remain on `group.calls`: transcript
 * supersession reads that collection independently of this presentation split.
 */
export function projectToolGroup(group: ToolCallGroup): ToolGroupPresentation {
  const rowCalls = group.calls.filter((call) => !isStandalonePayload(call))
  const standalonePayloads = group.calls
    .filter(isStandalonePayload)
    .map((call) => ({
      key: call.localId,
      call,
      value: call.value ?? "",
      valueType: call.valueType ?? "html",
      showRequest: false as const,
    }))
    .sort(
      (a, b) =>
        (a.call.resolveBlock ?? 0) - (b.call.resolveBlock ?? 0) ||
        (a.call.resolveIndex ?? 0) - (b.call.resolveIndex ?? 0),
    )

  if (rowCalls.length === 0) {
    return { row: null, standalonePayloads }
  }

  // Lifecycle groups already carry the identity derived from their complete
  // call list. Preserve it when every call remains in the row so callers of
  // the public group model retain its established contract; a migrated row is
  // the only case where the identity must be re-derived from a strict subset.
  const identity =
    standalonePayloads.length === 0
      ? {
          title: group.title,
          titleSettled: group.titleSettled,
          icon: group.icon,
          count: group.count,
          segments: group.segments,
        }
      : deriveToolGroupIdentity(rowCalls)
  return {
    row: {
      calls: rowCalls,
      identity,
      single: rowCalls.length === 1 ? rowCalls[0]! : null,
      anyRunning: rowCalls.some((call) => call.status === "running"),
      failedCount: rowCalls.filter((call) => call.status === "error").length,
      heterogeneous: identity.segments.length > 1,
      hasExpandedCall: rowCalls.some((call) => call.expanded),
      segmentTitles: new Map(
        identity.segments.map((segment) => [segment.toolName, segment.title]),
      ),
    },
    standalonePayloads,
  }
}
