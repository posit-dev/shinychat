import { memo, useMemo, useRef, useState } from "react"
import { ToolCard } from "./ToolCard"
import { ChevronIcon } from "./ChevronIcon"
import { RawHTML } from "./RawHTML"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { highlightHtmlCode } from "../markdown/highlightHtmlCode"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"
import { exclamationCircleFill, filePdfFill } from "../utils/icons"
import { useFullscreen } from "./useFullscreen"
import { useChatStopScroll } from "./context"

interface ContentExtraItem {
  type: "image" | "pdf" | "text"
  src?: string
  filename?: string
  value?: string
  value_type?: "html" | "markdown" | "text" | "code"
}

function PdfBadge({ filename }: { filename: string }) {
  return (
    <div className="shiny-chat-pdf badge fs-6 text-bg-secondary">
      <span
        className="shiny-chat-pdf__icon me-1"
        dangerouslySetInnerHTML={{ __html: filePdfFill }}
      />
      <span className="shiny-chat-pdf__filename font-monospace">
        {filename}
      </span>
    </div>
  )
}

function ContentExtraText({
  value,
  valueType,
}: {
  value: string
  valueType: string
}) {
  if (valueType === "html") {
    return <RawHTML html={value} />
  } else if (valueType === "text") {
    return <p>{value}</p>
  } else if (valueType === "markdown") {
    return (
      <MarkdownContent
        content={value}
        contentType="markdown"
        streaming={false}
      />
    )
  }
  return (
    <MarkdownContent
      content={markdownCodeBlock(value.trimEnd(), "text")}
      contentType="markdown"
      streaming={false}
    />
  )
}

export interface ToolResultProps {
  toolName: string
  toolTitle?: string
  label?: string
  intent?: string
  status: string
  value: string
  valueType: string
  requestCall?: string
  showRequest?: boolean
  fullScreen?: boolean
  initialExpanded?: boolean
  icon?: string
  footer?: string
  details?: string
  detailsType?: "html" | "markdown"
  detailsSummary?: string
  detailsOpen?: boolean
}

export const ToolResult = memo(function ToolResult({
  toolName,
  toolTitle,
  label,
  intent,
  status,
  value,
  valueType,
  requestCall,
  showRequest = false,
  fullScreen = false,
  initialExpanded = false,
  icon: iconProp,
  footer,
  details,
  detailsType,
  detailsSummary,
  detailsOpen,
}: ToolResultProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const { enterFullscreen, overlay } = useFullscreen(cardRef)
  const stopScroll = useChatStopScroll()

  const isError = status === "error"
  const classStatus = isError ? "text-danger" : ""
  const icon = isError ? exclamationCircleFill : iconProp

  const isMarkdownDetails = detailsType === "markdown"

  // Same treatment as html result bodies: language-tagged code blocks get
  // highlighted once, memoized so disclosure toggles don't re-parse. The
  // markdown flavor highlights through MarkdownContent's own pipeline.
  const highlightedDetails = useMemo(
    () =>
      details && !isMarkdownDetails ? highlightHtmlCode(details) : details,
    [details, isMarkdownDetails],
  )

  // The `<details>` is uncontrolled (its `open` attr is only the initial
  // state), so mirror toggles into state for the chevron's rotation.
  const [detailsExpanded, setDetailsExpanded] = useState(detailsOpen ?? false)

  return (
    <>
      <ToolCard
        toolName={toolName}
        toolTitle={toolTitle}
        label={label}
        intent={intent}
        icon={icon}
        classStatus={classStatus}
        statusNote={isError ? "failed" : undefined}
        fullScreen={fullScreen}
        initialExpanded={initialExpanded}
        footer={footer}
        onEnterFullscreen={enterFullscreen}
        cardRef={cardRef}
        // Body errors can derive from any of these inputs. The boundary must
        // retry when any of them changes, not just the result value.
        resetKey={`${valueType}${showRequest}${requestCall}${value}${details}${detailsType}`}
      >
        {/* A component (not an inline call) so a malformed requestCall throws
            below ToolCard's body boundary and the card header survives. */}
        <ToolRequestDetails
          requestCall={requestCall}
          showRequest={showRequest}
          stopScroll={stopScroll}
        />
        {highlightedDetails && (
          <div className="shiny-tool-result__details">
            <details
              open={detailsOpen || undefined}
              onToggle={(e) => {
                setDetailsExpanded(e.currentTarget.open)
                stopScroll?.()
              }}
            >
              <summary>
                <ChevronIcon
                  className="shiny-tool-result__details-chevron"
                  expanded={detailsExpanded}
                />
                {detailsSummary ?? "Details"}
              </summary>
              {isMarkdownDetails ? (
                <MarkdownContent
                  content={highlightedDetails}
                  contentType="markdown"
                  streaming={false}
                />
              ) : (
                <RawHTML html={highlightedDetails} />
              )}
            </details>
          </div>
        )}
        <ToolResultValue
          value={value}
          valueType={valueType}
          showRequest={showRequest}
        />
      </ToolCard>
      {overlay}
    </>
  )
})

function ToolRequestDetails({
  requestCall,
  showRequest,
  stopScroll,
}: {
  requestCall: string | undefined
  showRequest: boolean
  stopScroll: ReturnType<typeof useChatStopScroll>
}): React.ReactNode {
  if (!showRequest || !requestCall) {
    return null
  }

  const requestMarkdown = markdownCodeBlock(requestCall, "")
  const isLongRequest = requestCall.split("\n").length > 2

  return (
    <div className="shiny-tool-result__request">
      {isLongRequest ? (
        <details onToggle={() => stopScroll?.()}>
          <summary>Tool call</summary>
          <MarkdownContent
            content={requestMarkdown}
            contentType="markdown"
            streaming={false}
          />
        </details>
      ) : (
        <>
          <strong>Tool call</strong>
          <MarkdownContent
            content={requestMarkdown}
            contentType="markdown"
            streaming={false}
          />
        </>
      )}
    </div>
  )
}

/**
 * The Tier-3 value: maps `value`/`valueType` to rendered content. Exported so
 * `ToolGroup` can reuse the exact same path for a migrated custom-display
 * payload — that path is `valueType === "html"` with `showRequest` false,
 * which is already the one case below that returns with no card chrome.
 */
export function ToolResultValue({
  value,
  valueType,
  showRequest,
}: {
  value: string
  valueType: string
  showRequest: boolean
}): React.ReactNode {
  // Console results conventionally end with a newline (e.g. R's `cat()`);
  // inside a fenced block it renders as a trailing blank line that reads as
  // double bottom padding, so drop it for display.
  const displayValue = value.trimEnd() || "[Empty result]"

  // HTML values can embed multi-MB base64 images; keep the parse/highlight
  // round-trip out of unrelated re-renders.
  const highlightedHtml = useMemo(
    () =>
      valueType === "html" ? highlightHtmlCode(displayValue) : displayValue,
    [valueType, displayValue],
  )

  let resultContent: React.ReactNode

  if (valueType === "html") {
    resultContent = <RawHTML html={highlightedHtml} />
  } else if (valueType === "text") {
    resultContent = <p>{displayValue}</p>
  } else if (valueType === "content_extra") {
    try {
      const items = JSON.parse(value) as ContentExtraItem[]
      resultContent = (
        <div className="shiny-chat-content-extra">
          {items.map((item, i) => {
            if (item.type === "image") {
              return (
                <img key={i} src={item.src} className="shiny-chat-tool-image" />
              )
            } else if (item.type === "pdf") {
              return <PdfBadge key={i} filename={item.filename ?? ""} />
            } else if (item.type === "text") {
              return (
                <ContentExtraText
                  key={i}
                  value={item.value ?? ""}
                  valueType={item.value_type ?? "code"}
                />
              )
            }
            return null
          })}
        </div>
      )
    } catch {
      resultContent = (
        <MarkdownContent
          content={markdownCodeBlock(displayValue, "text")}
          contentType="markdown"
          streaming={false}
        />
      )
    }
  } else {
    const markdownContent =
      valueType !== "markdown"
        ? markdownCodeBlock(displayValue, "text")
        : displayValue

    resultContent = (
      <MarkdownContent
        content={markdownContent}
        contentType="markdown"
        streaming={false}
      />
    )
  }

  if (!showRequest && valueType === "html") {
    return resultContent
  }

  const resultHeader = showRequest ? <strong>Tool result</strong> : null

  return (
    <div className="shiny-tool-result__result">
      {resultHeader}
      {resultContent}
    </div>
  )
}
