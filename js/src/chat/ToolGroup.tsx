import {
  Fragment,
  memo,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react"
import type { ToolCallGroup, ToolCallItem, ToolCallSegment } from "./state"
import { ToolResult } from "./ToolResult"
import { ToolRequest } from "./ToolRequest"
import { ChatDispatchContext } from "./context"
import { bareDot, chevronDown, exclamationCircleFill } from "../utils/icons"

const spinnerHtml =
  '<div class="spinner-border" role="status"><span class="visually-hidden">Running…</span></div>'
const checkHtml =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l1.093 1.093 3.473-4.425z"/></svg>'

const chevronDSIH = { __html: chevronDown }

// Truncate a scalar argument value for use as a fallback per-call label.
// A dictionary-style preview of a call's arguments: up to the first three
// scalar args as "key: value", skipping internal keys (those starting with "_"
// or "."). Truncated as a whole to keep the row compact.
const ARG_PREVIEW_MAX = 40
function argPreview(argsJson?: string): string | null {
  if (!argsJson) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(argsJson)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object") return null
  const parts: string[] = []
  for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
    if (k.startsWith("_") || k.startsWith(".")) continue
    if (
      typeof v === "string" ||
      typeof v === "number" ||
      typeof v === "boolean"
    ) {
      parts.push(`${k}: ${v}`)
      if (parts.length === 3) break
    }
  }
  if (parts.length === 0) return null
  const s = parts.join(", ")
  return s.length > ARG_PREVIEW_MAX ? `${s.slice(0, ARG_PREVIEW_MAX - 1)}…` : s
}

interface PerCallLabel {
  text: string
  code?: boolean
}

// The per-call row label: an explicit `label`, else the call's full dynamic
// (result) title when it adds information beyond the header, else a
// dictionary-style argument preview, else the tool name. For a single-call row
// the title is already shown as the header, so the arg preview only stands in
// for a bare tool with no title.
//
// `segmentTitle` is the header title for *this call's tool* — not the whole
// header, which for a heterogeneous group names several tools and would both
// fail to suppress a repeat and suppress an unrelated tool's title.
function perCallLabel(
  item: ToolCallItem,
  segmentTitle: string | undefined,
  isSingle: boolean,
): PerCallLabel | null {
  if (item.label) return { text: item.label }
  if (!isSingle && item.title && item.title !== segmentTitle) {
    return { text: item.title }
  }
  if (isSingle && segmentTitle) return null
  const ap = argPreview(item.arguments)
  if (ap) return { text: ap, code: true }
  // Nothing identifying left (a bare no-argument tool). A Tier-2 row would
  // otherwise be an unnamed glyph + chevron button, so fall back to the tool
  // name in code font — the same fallback `GroupTitle` uses for the header. A
  // single-call row already carries it in the header, so it stays bare there.
  if (!isSingle) return { text: item.toolName, code: true }
  return null
}

// Open state for a disclosure row that honors a server-provided `expanded`
// flag. Seeding `useState` alone isn't enough: `expanded` arrives on the result
// element, which can land after the row already mounted for the request. So
// latch open when the flag turns on. It only ever opens — a user collapse is
// not undone, because the flag doesn't transition again.
function useExpandable(
  expanded: boolean | undefined,
): [boolean, (update: (v: boolean) => boolean) => void] {
  const [open, setOpen] = useState(expanded ?? false)
  const wasExpanded = useRef(expanded ?? false)
  useEffect(() => {
    if (expanded && !wasExpanded.current) setOpen(true)
    wasExpanded.current = expanded ?? false
  }, [expanded])
  return [open, setOpen]
}

// The icon this particular result returned, as opposed to the one its tool
// definition carries. The servers emit the result's `icon` as
// `display.icon ?? annotations.icon`, so it identifies *this call* only when it
// differs from the definition icon the request element carries.
function resultSpecificIcon(item: ToolCallItem): string | undefined {
  if (!item.icon || item.icon === item.definitionIcon) return undefined
  return item.icon
}

function statusGlyphHtml(status: ToolCallItem["status"]): string {
  if (status === "running") return spinnerHtml
  if (status === "error") return exclamationCircleFill
  return checkHtml
}

// The Tier-3 leaf: the full request/result card, reusing the existing tool
// components. `open` forces the card body visible (used under a Tier-2 row).
function renderLeaf(item: ToolCallItem, open: boolean): ReactNode {
  if (item.status === "running") {
    return (
      <ToolRequest
        toolName={item.toolName}
        toolTitle={item.title ?? item.definitionTitle}
        intent={item.intent}
        arguments={item.arguments ?? "{}"}
      />
    )
  }
  return (
    <ToolResult
      toolName={item.toolName}
      toolTitle={item.title ?? item.definitionTitle}
      intent={item.intent}
      status={item.status}
      value={item.value ?? ""}
      valueType={item.valueType ?? "markdown"}
      requestCall={item.requestCall}
      showRequest={item.showRequest}
      fullScreen={item.fullScreen}
      expanded={open || item.expanded}
      icon={item.icon}
      footer={item.footer}
      label={item.label}
    />
  )
}

// One tool's stretch of the header: its title (or the bare tool name), then its
// own ×N. The title is `dangerouslySetInnerHTML` because server-provided titles
// may carry markup.
function TitleSegment({
  segment,
  showVerb,
}: {
  segment: ToolCallSegment
  showVerb: boolean
}): ReactNode {
  return (
    <>
      {segment.title ? (
        <span
          className="shinychat-tool-group__title"
          dangerouslySetInnerHTML={{ __html: segment.title }}
        />
      ) : (
        <>
          {/* Same monotonic present→past latch the definition→result title
              swap follows, scoped to this tool's calls. */}
          {showVerb && (segment.settled ? "Used " : "Using ")}
          <code className="shinychat-tool-group__toolname">
            {segment.toolName}
          </code>
        </>
      )}
      {segment.count > 1 && (
        <span
          className="shinychat-tool-group__count"
          aria-label={`${segment.count} calls`}
        >
          {`×${segment.count}`}
        </span>
      )}
    </>
  )
}

// A heterogeneous group can name arbitrarily many tools and has one row to do
// it in. Segments are shown whole or not at all — a header of independently
// ellipsized titles ("Net revenue, last fo…, Exported th…, Emailed the s…") is
// noise, so the ones that don't fit fold into "and N others" instead.
//
// The limit is a character budget over the visible text, not a measured width:
// the header stays a pure function of its content, needing no layout read and
// no re-measure on resize. The segment cap is a backstop for short titles, where
// a long list can fit the budget and still read as a crowd.
const SEGMENT_CHAR_BUDGET = 60
const MAX_SEGMENTS = 3

// Titles may carry markup, so measure what the reader actually sees.
function segmentTextLength(segment: ToolCallSegment): number {
  const text = segment.title
    ? segment.title.replace(/<[^>]*>/g, "")
    : `Used ${segment.toolName}`
  return text.length + (segment.count > 1 ? `×${segment.count}`.length : 0)
}

function visibleSegments(segments: ToolCallSegment[]): {
  shown: ToolCallSegment[]
  hidden: number
} {
  const shown: ToolCallSegment[] = []
  let used = 0
  for (const segment of segments) {
    const cost = segmentTextLength(segment) + (shown.length ? ", ".length : 0)
    // The first segment is always shown, however long it is: a header of
    // nothing but "and N others" would name nothing at all. Its overflow is
    // absorbed by the joined list's ellipsis instead.
    const full =
      shown.length >= MAX_SEGMENTS || used + cost > SEGMENT_CHAR_BUDGET
    if (shown.length && full) break
    shown.push(segment)
    used += cost
  }
  return { shown, hidden: segments.length - shown.length }
}

// The group header's identity. A heterogeneous ("all") group holds several
// tools, so it names each one with its own count — the same titles the tools
// would show ungrouped — joined by ", ". A homogeneous group has a single
// segment and renders exactly as it always has: the title span (plus its ×N),
// unwrapped, straight into the row's flex layout.
function GroupTitle({ group }: { group: ToolCallGroup }): ReactNode {
  const segments = group.segments

  if (segments.length === 1) {
    return <TitleSegment segment={segments[0]!} showVerb={true} />
  }

  const { shown, hidden } = visibleSegments(segments)
  // With nothing titled the verbs would stack up ("Used a ×2, Used b ×3"); a
  // single leading verb reads as covering the whole list. As soon as one tool
  // has a title the list is no longer a plain enumeration, so each untitled
  // segment keeps its own verb. Judged on what's rendered, since that's what
  // the reader sees.
  const anyTitled = shown.some((s) => s.title)

  return (
    <span className="shinychat-tool-group__segments">
      {shown.map((segment, i) => (
        <Fragment key={segment.toolName}>
          {i > 0 && ", "}
          <span className="shinychat-tool-group__segment">
            <TitleSegment segment={segment} showVerb={anyTitled || i === 0} />
          </span>
        </Fragment>
      ))}
      {hidden > 0 && (
        <span className="shinychat-tool-group__overflow">
          {`, and ${hidden} ${hidden === 1 ? "other" : "others"}`}
        </span>
      )}
    </span>
  )
}

// A single-call group is itself the leaf, but it still rests as a quiet Tier-1
// row (glyph + title + label + peek + chevron) that morphs straight into the
// full card on expand — matching a collapsed multi-call group rather than
// standing out as a bare card.
function SingleCallRow({
  group,
  item,
}: {
  group: ToolCallGroup
  item: ToolCallItem
}): ReactNode {
  const [open, setOpen] = useExpandable(item.expanded)
  const running = item.status === "running"
  const failed = item.status === "error"
  const label = perCallLabel(item, group.title, true)
  const glyphHtml = running ? spinnerHtml : group.icon || bareDot
  // Not derived from `item.requestId`: it is optional, and a request can
  // render in a different message than its result before pairing settles.
  const contentId = `tool-call${useId()}`

  return (
    <div className="shinychat-tool-group shinychat-tool-group--single">
      <button
        type="button"
        className="shinychat-tool-group__row"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`shinychat-tool-group__glyph${running ? " running" : ""}`}
          dangerouslySetInnerHTML={{ __html: glyphHtml }}
        />
        <span className="shinychat-tool-group__titlewrap">
          <GroupTitle group={group} />
          {label && (
            <span className="shinychat-tool-group__label">
              {": "}
              {label.code ? <code>{label.text}</code> : label.text}
            </span>
          )}
        </span>
        <span className="shinychat-tool-spacer" />
        {open && item.intent && (
          <span className="shinychat-tool-row__intent">{item.intent}</span>
        )}
        {item.valuePreview && (
          <span className="shinychat-tool-call-row__preview">
            {item.valuePreview}
          </span>
        )}
        {failed && <span className="shinychat-tool-group__failed">failed</span>}
        <span
          className="shinychat-tool-group__chevron"
          dangerouslySetInnerHTML={chevronDSIH}
        />
      </button>
      <div
        id={contentId}
        className="shinychat-tool-call-row__detail"
        hidden={!open}
      >
        {open && renderLeaf(item, true)}
      </div>
    </div>
  )
}

function ToolCallRow({
  item,
  segmentTitle,
  heterogeneous,
}: {
  item: ToolCallItem
  segmentTitle: string | undefined
  /** True when the group spans several tools (see the glyph note below). */
  heterogeneous: boolean
}): ReactNode {
  const [open, setOpen] = useExpandable(item.expanded)
  const label = perCallLabel(item, segmentTitle, false)
  const statusClass =
    item.status === "error"
      ? " text-danger"
      : item.status === "running"
        ? " running"
        : ""
  // The glyph carries identity where identity varies and status where identity
  // is constant. A running call always shows the spinner (progress is the more
  // urgent fact). Otherwise an icon this result returned for itself wins — it is
  // the most specific thing known about the call, and the group header can never
  // show it. Failing that, a group spanning several tools has no header icon to
  // name one, so each row wears its own tool's icon; a homogeneous group's rows
  // keep pure status vocabulary. `statusClass` still applies: a failed row tints
  // whichever glyph it ends up with, and it keeps the "failed" note below, so
  // failure stays legible even when an icon replaces the exclamation.
  const glyphHtml =
    item.status === "running"
      ? spinnerHtml
      : (resultSpecificIcon(item) ??
        (heterogeneous
          ? item.icon || item.definitionIcon || statusGlyphHtml(item.status)
          : statusGlyphHtml(item.status)))
  // Not derived from `item.requestId`: it is optional, and a request can
  // render in a different message than its result before pairing settles.
  const contentId = `tool-call${useId()}`

  return (
    <li className="shinychat-tool-call-row" role="listitem">
      <button
        type="button"
        className="shinychat-tool-call-row__summary"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`shinychat-tool-call-row__status${statusClass}`}
          dangerouslySetInnerHTML={{ __html: glyphHtml }}
        />
        {label && (
          <span className="shinychat-tool-call-row__label">
            {label.code ? <code>{label.text}</code> : label.text}
          </span>
        )}
        <span className="shinychat-tool-spacer" />
        {open && item.intent && (
          <span className="shinychat-tool-row__intent">{item.intent}</span>
        )}
        {item.valuePreview && (
          <span className="shinychat-tool-call-row__preview">
            {item.valuePreview}
          </span>
        )}
        {/* The red status glyph is decorative (aria-hidden), so a failed row
            also carries the same subtle text note the single-call row uses —
            otherwise only the group header says anything failed, never which
            row. */}
        {item.status === "error" && (
          <span className="shinychat-tool-group__failed">failed</span>
        )}
        <span
          className="shinychat-tool-call-row__chevron"
          dangerouslySetInnerHTML={chevronDSIH}
        />
      </button>
      <div
        id={contentId}
        className="shinychat-tool-call-row__detail"
        hidden={!open}
      >
        {open && renderLeaf(item, true)}
      </div>
    </li>
  )
}

export const ToolGroup = memo(function ToolGroup({
  group,
}: {
  group: ToolCallGroup
}) {
  // A call marked `expanded` must be reachable: open the group so its Tier-2
  // row (which opens itself) isn't stranded inside the hidden call list.
  const [expanded, setExpanded] = useExpandable(
    group.calls.some((c) => c.expanded),
  )
  const dispatch = useContext(ChatDispatchContext)
  // `group.key` is only unique within one routed loop, so it can't seed a
  // document-wide `id`: two messages that both group "all" (or repeat a tool
  // name) would point their rows' `aria-controls` at the same region.
  const listId = `tool-group${useId()}`

  // A rendered result supersedes its matching request wherever it lives (often
  // a separate/preloaded message the per-message router can't collapse), so
  // hide that request — mirroring the pre-refactor ToolResultBridge behavior.
  useEffect(() => {
    if (!dispatch) return
    for (const c of group.calls) {
      if (c.status !== "running" && c.requestId) {
        dispatch({ type: "hide_tool_request", requestId: c.requestId })
      }
    }
  }, [dispatch, group.calls])

  // A single-call group rests as a quiet Tier-1 row (skipping Tier 2) and
  // morphs into the full card on expand.
  if (group.calls.length === 1) {
    return <SingleCallRow group={group} item={group.calls[0]!} />
  }

  const anyRunning = group.calls.some((c) => c.status === "running")
  const failedCount = group.calls.filter((c) => c.status === "error").length
  // A group spanning several tools has no one icon to show, so the header
  // keeps the generic dot and lets the rows carry the tool icons instead.
  const heterogeneous = group.segments.length > 1
  const glyphHtml = anyRunning
    ? spinnerHtml
    : heterogeneous
      ? bareDot
      : group.icon || bareDot
  // A row must not repeat a title its own segment already shows, so it compares
  // against that tool's segment title rather than the combined header.
  const segmentTitles = new Map(
    group.segments.map((s) => [s.toolName, s.title]),
  )

  return (
    <div className="shinychat-tool-group shinychat-tool-group--multi">
      <button
        type="button"
        className="shinychat-tool-group__row"
        aria-expanded={expanded}
        aria-controls={listId}
        onClick={() => setExpanded((v) => !v)}
      >
        <span
          className={`shinychat-tool-group__glyph${anyRunning ? " running" : ""}`}
          dangerouslySetInnerHTML={{ __html: glyphHtml }}
        />
        {/* The ×N lives inside the header, one per tool: a heterogeneous group
            has no single count to show, and a homogeneous one has exactly one
            segment, so its badge lands in the same place as before. */}
        <GroupTitle group={group} />
        {failedCount > 0 && (
          <span className="shinychat-tool-group__failed">
            {`${failedCount} failed`}
          </span>
        )}
        <span className="shinychat-tool-spacer" />
        <span
          className="shinychat-tool-group__chevron"
          dangerouslySetInnerHTML={chevronDSIH}
        />
      </button>
      <ul
        id={listId}
        className="shinychat-tool-group__calls"
        role="list"
        hidden={!expanded}
      >
        {group.calls.map((item) => (
          <ToolCallRow
            key={item.localId}
            item={item}
            segmentTitle={segmentTitles.get(item.toolName)}
            heterogeneous={heterogeneous}
          />
        ))}
      </ul>
    </div>
  )
})
