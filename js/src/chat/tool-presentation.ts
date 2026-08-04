import {
  deriveToolGroupIdentity,
  type ToolCallGroup,
  type ToolCallItem,
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

function isStandalonePayload(call: ToolCallItem): boolean {
  return call.customDisplay === true && call.status !== "running"
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
