import { memo, useContext, useEffect, useState, type ReactNode } from "react"
import type { ToolCallGroup, ToolCallItem } from "./state"
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
function argPreview(argsJson?: string): string | null {
  if (!argsJson) return null
  let parsed: unknown
  try {
    parsed = JSON.parse(argsJson)
  } catch {
    return null
  }
  if (!parsed || typeof parsed !== "object") return null
  for (const v of Object.values(parsed as Record<string, unknown>)) {
    if (
      typeof v === "string" ||
      typeof v === "number" ||
      typeof v === "boolean"
    ) {
      const s = String(v)
      return s.length > 40 ? `${s.slice(0, 39)}…` : s
    }
  }
  return null
}

// Remainder of a per-call title after stripping the group title's common
// prefix, but only when the match ends on a word boundary (so "Searching
// glucose" − "Searching" → "glucose", while a tense mismatch yields nothing).
function stripCommonPrefix(title: string, groupTitle: string): string | null {
  if (!groupTitle) return null
  let i = 0
  const n = Math.min(title.length, groupTitle.length)
  while (i < n && title[i] === groupTitle[i]) i++
  const atBoundary =
    i === groupTitle.length || title[i] === " " || title[i - 1] === " "
  if (!atBoundary) return null
  const remainder = title.slice(i).trim()
  return remainder && remainder !== title.trim() ? remainder : null
}

interface PerCallLabel {
  text: string
  code?: boolean
}

function perCallLabel(
  item: ToolCallItem,
  groupTitle: string | undefined,
): PerCallLabel | null {
  if (item.label) return { text: item.label }
  if (item.title && groupTitle) {
    const rem = stripCommonPrefix(item.title, groupTitle)
    if (rem) return { text: rem }
  }
  const ap = argPreview(item.arguments)
  if (ap) return { text: ap, code: true }
  return null
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
        requestId={item.requestId}
        toolName={item.toolName}
        toolTitle={item.title}
        intent={item.intent}
        arguments={item.arguments ?? "{}"}
      />
    )
  }
  return (
    <ToolResult
      requestId={item.requestId}
      toolName={item.toolName}
      toolTitle={item.title}
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

function GroupTitle({ group }: { group: ToolCallGroup }): ReactNode {
  if (group.title) {
    return (
      <span
        className="shinychat-tool-group__title"
        dangerouslySetInnerHTML={{ __html: group.title }}
      />
    )
  }
  return (
    <code className="shinychat-tool-group__toolname">{group.toolName}</code>
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
  const [open, setOpen] = useState(item.expanded ?? false)
  const running = item.status === "running"
  const failed = item.status === "error"
  const label = perCallLabel(item, group.title)
  const glyphHtml = running ? spinnerHtml : group.icon || bareDot
  const contentId = `tool-call-${item.requestId}`

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
        {item.valuePreview && (
          <span className="shinychat-tool-call-row__preview">
            {item.valuePreview}
          </span>
        )}
        <span className="shinychat-tool-spacer" />
        {open && item.intent && (
          <span className="shinychat-tool-row__intent">{item.intent}</span>
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
  groupTitle,
}: {
  item: ToolCallItem
  groupTitle: string | undefined
}): ReactNode {
  const [open, setOpen] = useState(false)
  const label = perCallLabel(item, groupTitle)
  const statusClass =
    item.status === "error"
      ? " text-danger"
      : item.status === "running"
        ? " running"
        : ""
  const contentId = `tool-call-${item.requestId}`

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
          dangerouslySetInnerHTML={{ __html: statusGlyphHtml(item.status) }}
        />
        {label && (
          <span className="shinychat-tool-call-row__label">
            {label.code ? <code>{label.text}</code> : label.text}
          </span>
        )}
        {item.valuePreview && (
          <span className="shinychat-tool-call-row__preview">
            {item.valuePreview}
          </span>
        )}
        <span className="shinychat-tool-spacer" />
        {open && item.intent && (
          <span className="shinychat-tool-row__intent">{item.intent}</span>
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
  const [expanded, setExpanded] = useState(false)
  const dispatch = useContext(ChatDispatchContext)

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
  const glyphHtml = anyRunning ? spinnerHtml : group.icon || bareDot
  const listId = `tool-group-${group.key}`

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
        <GroupTitle group={group} />
        {group.count > 1 && (
          <span
            className="shinychat-tool-group__count"
            aria-label={`${group.count} calls`}
          >
            {`×${group.count}`}
          </span>
        )}
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
            key={item.requestId}
            item={item}
            groupTitle={group.title}
          />
        ))}
      </ul>
    </div>
  )
})
