import {
  Fragment,
  memo,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react"
import {
  type ToolCallGroup,
  type ToolCallItem,
  type ToolCallSegment,
} from "./tool-model"
import { projectToolGroup, type ToolGroupRowView } from "./tool-presentation"
import { ToolResult, ToolResultValue } from "./ToolResult"
import { ToolRequest } from "./ToolRequest"
import { useFadingValue } from "./useFadingText"
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

// The naming half of a segment: the author's title, or the verb plus the bare
// tool name when there isn't one. Both forms live in one element so the
// present→past swap crossfades as a unit — fading the verb alone would leave
// the tool name visibly jumping sideways as "Using" narrows to "Used".
interface SegmentName {
  title?: string
  verb: string
  toolName: string
}

function segmentName(segment: ToolCallSegment, showVerb: boolean): SegmentName {
  return {
    title: segment.title,
    // Same monotonic present→past latch the definition→result title swap
    // follows, scoped to this tool's calls.
    verb: showVerb ? (segment.settled ? "Used " : "Using ") : "",
    toolName: segment.toolName,
  }
}

// Everything the rendered name depends on. The count is deliberately absent:
// it sits outside the fading element, so a call landing shouldn't blink the
// title.
function segmentNameKey(name: SegmentName): string {
  return name.title != null
    ? `title:${name.title}`
    : `tool:${name.verb}|${name.toolName}`
}

// One tool's stretch of the header: its name, then its own ×N. A title is
// `dangerouslySetInnerHTML` because server-provided titles may carry markup.
function TitleSegment({
  segment,
  showVerb,
}: {
  segment: ToolCallSegment
  showVerb: boolean
}): ReactNode {
  const name = segmentName(segment, showVerb)
  // A tool's title changes under it as the call settles (the definition title
  // gives way to the result's), the same way the thinking header's does. Swap
  // it behind a crossfade rather than having it flip mid-row.
  const { visible, fading } = useFadingValue(name, segmentNameKey(name))
  const nameProps = {
    className: "shiny-chat-tool-group__title",
    "data-fading": fading || undefined,
  }

  return (
    <>
      {visible.title != null ? (
        <span
          {...nameProps}
          dangerouslySetInnerHTML={{ __html: visible.title }}
        />
      ) : (
        <span {...nameProps}>
          {visible.verb}
          <code className="shiny-chat-tool-group__toolname">
            {visible.toolName}
          </code>
        </span>
      )}
      {segment.count > 1 && (
        <span
          className="shiny-chat-tool-group__count"
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
function GroupTitle({ segments }: { segments: ToolCallSegment[] }): ReactNode {
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
    <span className="shiny-chat-tool-group__segments">
      {shown.map((segment, i) => (
        <Fragment key={segment.toolName}>
          {i > 0 && ", "}
          <span className="shiny-chat-tool-group__segment">
            <TitleSegment segment={segment} showVerb={anyTitled || i === 0} />
          </span>
        </Fragment>
      ))}
      {hidden > 0 && (
        <span className="shiny-chat-tool-group__overflow">
          {`, and ${hidden} ${hidden === 1 ? "other" : "others"}`}
        </span>
      )}
    </span>
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
    <li className="shiny-chat-tool-call-row" role="listitem">
      <button
        type="button"
        className="shiny-chat-tool-call-row__summary"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => setOpen((v) => !v)}
      >
        <span
          className={`shiny-chat-tool-call-row__status${statusClass}`}
          dangerouslySetInnerHTML={{ __html: glyphHtml }}
        />
        {label && (
          <span className="shiny-chat-tool-call-row__label">
            {label.code ? <code>{label.text}</code> : label.text}
          </span>
        )}
        <span className="shiny-chat-tool-spacer" />
        {open && item.intent && (
          <span className="shiny-chat-tool-row__intent">{item.intent}</span>
        )}
        {item.valuePreview && (
          <span className="shiny-chat-tool-call-row__preview">
            {item.valuePreview}
          </span>
        )}
        {/* The red status glyph is decorative (aria-hidden), so a failed row
            also carries the same subtle text note the single-call row uses —
            otherwise only the group header says anything failed, never which
            row. */}
        {item.status === "error" && (
          <span className="shiny-chat-tool-group__failed">failed</span>
        )}
        <span
          className="shiny-chat-tool-call-row__chevron"
          dangerouslySetInnerHTML={chevronDSIH}
        />
      </button>
      <div
        id={contentId}
        className="shiny-chat-tool-call-row__detail"
        hidden={!open}
      >
        {open && renderLeaf(item, true)}
      </div>
    </li>
  )
}

// One Tier-1 activity row, whether the group holds a single call or many.
//
// A single-call group is itself the leaf: the row opens straight into the full
// card, skipping Tier 2. A multi-call group opens into its list of Tier-2 rows
// instead. Both shapes are one component on purpose — React reconciles by
// position and type, so rendering them as two components tore the whole subtree
// down the moment a group grew from one call to two (the default, as soon as a
// tool is called twice). That discarded every row's expand state and remounted
// the header, which is exactly where the title crossfade belongs: `resolveTitle`
// swaps the call's own dynamic result title for the tool's static definition
// title at that boundary ("Weather for Portland" → "Weather Forecast ×2").
//
// So the shell down to the title element is identical in both shapes; only the
// trailing row elements and the body below the row differ.
export const ToolGroup = memo(function ToolGroup({
  group,
}: {
  group: ToolCallGroup
}) {
  const { row, standalonePayloads } = projectToolGroup(group)
  const [expanded, setExpanded] = useExpandable(row?.hasExpandedCall)
  // Not seeded from `group.key` or a call's `requestId`: `group.key` is only
  // unique within one routed loop (two messages that both group "all", or
  // repeat a tool name, would point their rows' `aria-controls` at the same
  // region), and a request id is optional and can render in a different message
  // than its result before pairing settles.
  const bodyId = `tool-group${useId()}`

  // A rendered result supersedes its matching request wherever it lives, but
  // that is not this component's job to announce: ChatApp derives it from the
  // transcript (`supersededRequestIds`). Rendering used to dispatch it as a
  // side effect, which is why the row it superseded could unmount mid-render.

  return (
    <>
      {/* Fragment adds no DOM, so `.shiny-chat-tool-group` stays a direct child
          of `.shiny-chat-tool-loop` when it renders at all — existing CSS keyed
          on that relationship is unaffected. When every call has migrated out
          there is nothing left for the row to show, so it disappears rather
          than rendering empty. */}
      {row && (
        <ToolGroupRow
          row={row}
          expanded={expanded}
          setExpanded={setExpanded}
          bodyId={bodyId}
        />
      )}
      {standalonePayloads.map((payload) => (
        <div key={payload.key} className="shiny-chat-tool-custom-display">
          <ToolResultValue
            value={payload.value}
            valueType={payload.valueType}
            showRequest={payload.showRequest}
          />
        </div>
      ))}
    </>
  )
})

function ToolGroupRow({
  row,
  expanded,
  setExpanded,
  bodyId,
}: {
  row: ToolGroupRowView
  expanded: boolean
  setExpanded: (update: (v: boolean) => boolean) => void
  bodyId: string
}): ReactNode {
  const { identity, single, anyRunning, failedCount, heterogeneous } = row
  const label = single && perCallLabel(single, identity.title, true)
  // A group spanning several tools has no one icon to show, so the header
  // keeps the generic dot and lets the rows carry the tool icons instead.
  const glyphHtml = anyRunning
    ? spinnerHtml
    : heterogeneous
      ? bareDot
      : identity.icon || bareDot

  return (
    <div
      className={`shiny-chat-tool-group shiny-chat-tool-group--${
        single ? "single" : "multi"
      }`}
    >
      <button
        type="button"
        className="shiny-chat-tool-group__row"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => setExpanded((v) => !v)}
      >
        <span
          className={`shiny-chat-tool-group__glyph${anyRunning ? " running" : ""}`}
          dangerouslySetInnerHTML={{ __html: glyphHtml }}
        />
        {/* The title sits at this exact depth in both shapes, so it survives a
                1→N growth and can crossfade across it. The ×N lives inside the
                header, one per tool: a heterogeneous group has no single count to
                show, and a homogeneous one has exactly one segment, so its badge
                lands beside the title either way. */}
        <span className="shiny-chat-tool-group__titlewrap">
          <GroupTitle segments={identity.segments} />
          {label && (
            <span className="shiny-chat-tool-group__label">
              {": "}
              {label.code ? <code>{label.text}</code> : label.text}
            </span>
          )}
        </span>
        <span className="shiny-chat-tool-spacer" />
        {single && expanded && single.intent && (
          <span className="shiny-chat-tool-row__intent">{single.intent}</span>
        )}
        {single?.valuePreview && (
          <span className="shiny-chat-tool-call-row__preview">
            {single.valuePreview}
          </span>
        )}
        {/* One trailing slot for both shapes, so the note sits by the chevron
                whether the group holds one call or many. The status glyph is
                decorative (aria-hidden), so this text is the only cue a screen
                reader gets. */}
        {failedCount > 0 && (
          <span className="shiny-chat-tool-group__failed">
            {single ? "failed" : `${failedCount} failed`}
          </span>
        )}
        <span
          className="shiny-chat-tool-group__chevron"
          dangerouslySetInnerHTML={chevronDSIH}
        />
      </button>
      {single ? (
        <div
          id={bodyId}
          className="shiny-chat-tool-call-row__detail"
          hidden={!expanded}
        >
          {expanded && renderLeaf(single, true)}
        </div>
      ) : (
        <ul
          id={bodyId}
          className="shiny-chat-tool-group__calls"
          role="list"
          hidden={!expanded}
        >
          {row.calls.map((item) => (
            <ToolCallRow
              key={item.localId}
              item={item}
              segmentTitle={row.segmentTitles.get(item.toolName)}
              heterogeneous={heterogeneous}
            />
          ))}
        </ul>
      )}
    </div>
  )
}
