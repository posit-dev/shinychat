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
import {
  projectToolGroup,
  toolCallGlyph,
  toolCallLabel,
  toolGroupGlyph,
  toolHeaderSegments,
  toolSegmentName,
  toolSegmentNameKey,
  type ToolGlyph,
  type ToolGroupRowView,
} from "./tool-presentation"
import { ToolResult, ToolResultValue } from "./ToolResult"
import { ToolRequest } from "./ToolRequest"
import { useChatStopScroll } from "./context"
import { useFadingValue } from "./useFadingText"
import { bareDot, chevronDown, exclamationCircleFill } from "../utils/icons"

const spinnerHtml =
  '<div class="spinner-border" role="status"><span class="visually-hidden">Running…</span></div>'
const checkHtml =
  '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16" aria-hidden="true"><path d="M10.97 4.97a.75.75 0 0 1 1.07 1.05l-3.99 4.99a.75.75 0 0 1-1.08.02L4.324 8.384a.75.75 0 1 1 1.06-1.06l1.093 1.093 3.473-4.425z"/></svg>'

const chevronDSIH = { __html: chevronDown }

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

function statusGlyphHtml(status: ToolCallItem["status"]): string {
  if (status === "running") return spinnerHtml
  if (status === "error") return exclamationCircleFill
  return checkHtml
}

function glyphHtml(glyph: ToolGlyph): string {
  if (glyph.kind === "icon") return glyph.icon
  if (glyph.kind === "status") return statusGlyphHtml(glyph.status)
  return bareDot
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

// One tool's stretch of the header: its name, then its own ×N. A title is
// `dangerouslySetInnerHTML` because server-provided titles may carry markup.
function TitleSegment({
  segment,
  showVerb,
}: {
  segment: ToolCallSegment
  showVerb: boolean
}): ReactNode {
  const name = toolSegmentName(segment, showVerb)
  // A tool's title changes under it as the call settles (the definition title
  // gives way to the result's), the same way the thinking header's does. Swap
  // it behind a crossfade rather than having it flip mid-row.
  const { visible, fading } = useFadingValue(name, toolSegmentNameKey(name))
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

// The group header's identity. A heterogeneous ("all") group holds several
// tools, so it names each one with its own count — the same titles the tools
// would show ungrouped — joined by ", ". A homogeneous group has a single
// segment and renders exactly as it always has: the title span (plus its ×N),
// unwrapped, straight into the row's flex layout.
function GroupTitle({ segments }: { segments: ToolCallSegment[] }): ReactNode {
  if (segments.length === 1) {
    return <TitleSegment segment={segments[0]!} showVerb={true} />
  }

  const { shown, overflowText } = toolHeaderSegments(segments)
  return (
    <span className="shiny-chat-tool-group__segments">
      {shown.map(({ segment, showVerb }, i) => (
        <Fragment key={segment.toolName}>
          {i > 0 && ", "}
          <span className="shiny-chat-tool-group__segment">
            <TitleSegment segment={segment} showVerb={showVerb} />
          </span>
        </Fragment>
      ))}
      {overflowText && (
        <span className="shiny-chat-tool-group__overflow">{overflowText}</span>
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
  const stopScroll = useChatStopScroll()
  const framed =
    open && item.status === "success" && item.openStyle === "framed"
  const label = toolCallLabel(item, segmentTitle, false)
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
  const glyph = glyphHtml(toolCallGlyph(item, heterogeneous))
  // Not derived from `item.requestId`: it is optional, and a request can
  // render in a different message than its result before pairing settles.
  const contentId = `tool-call${useId()}`

  return (
    <li
      className={`shiny-chat-tool-call-row${
        framed ? " shiny-chat-tool-call-row--framed" : ""
      }`}
      role="listitem"
    >
      <button
        type="button"
        className="shiny-chat-tool-call-row__summary"
        aria-expanded={open}
        aria-controls={contentId}
        onClick={() => {
          stopScroll?.()
          setOpen((v) => !v)
        }}
      >
        <span
          className={`shiny-chat-tool-call-row__status${statusClass}`}
          dangerouslySetInnerHTML={{ __html: glyph }}
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
  const stopScroll = useChatStopScroll()
  const framed =
    expanded && single?.status === "success" && single.openStyle === "framed"
  const label = single && toolCallLabel(single, identity.title, true)
  const glyph = glyphHtml(toolGroupGlyph(row))

  return (
    <div
      className={`shiny-chat-tool-group shiny-chat-tool-group--${
        single ? "single" : "multi"
      }${framed ? " shiny-chat-tool-group--framed" : ""}`}
    >
      <button
        type="button"
        className="shiny-chat-tool-group__row"
        aria-expanded={expanded}
        aria-controls={bodyId}
        onClick={() => {
          stopScroll?.()
          setExpanded((v) => !v)
        }}
      >
        <span
          className={`shiny-chat-tool-group__glyph${anyRunning ? " running" : ""}`}
          dangerouslySetInnerHTML={{ __html: glyph }}
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
