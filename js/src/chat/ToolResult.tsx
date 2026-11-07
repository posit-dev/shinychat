import { memo, useEffect, useMemo, useRef, useState } from "react"
import { ToolCard } from "./ToolCard"
import { ChevronIcon } from "./ChevronIcon"
import { RawHTML } from "./RawHTML"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { CopyButton } from "../markdown/components/CopyButton"
import { highlightHtmlCode } from "../markdown/highlightHtmlCode"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"
import { exclamationCircleFill, filePdfFill } from "../utils/icons"
import {
  COPY_BUTTON_CLASS,
  copyTextToClipboard,
  createCopyButton,
  flashCopied,
} from "../utils/copyButton"
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
  requestCollapsed?: boolean
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
  requestCollapsed = false,
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

  const detailsRef = useRef<HTMLDivElement>(null)
  useDetailsCopyButtons(
    detailsRef,
    isMarkdownDetails ? undefined : highlightedDetails,
  )

  const detailsBodyRef = useRef<HTMLDivElement>(null)
  const singleCodeBlock = useSingleCodeBlock(detailsBodyRef, highlightedDetails)

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
          requestCollapsed={requestCollapsed}
          stopScroll={stopScroll}
        />
        {highlightedDetails && (
          <div
            className="shiny-tool-result__details"
            ref={detailsRef}
            {...(singleCodeBlock ? { "data-single-code-block": "" } : {})}
          >
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
              <div ref={detailsBodyRef}>
                {isMarkdownDetails ? (
                  <MarkdownContent
                    content={highlightedDetails}
                    contentType="markdown"
                    streaming={false}
                  />
                ) : (
                  <RawHTML html={highlightedDetails} />
                )}
              </div>
            </details>
            {/* Outside <summary> so clicking it can't toggle the disclosure
                (and a button nested in the toggle confuses assistive tech);
                CSS lays it over the summary row's right end. */}
            {singleCodeBlock && detailsExpanded && (
              <CopyButton
                getText={() =>
                  detailsBodyRef.current?.querySelector("pre")?.textContent ??
                  ""
                }
              />
            )}
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

/**
 * RawHTML opts out of React's DOM management, so the markdown pipeline's
 * CopyableCodeBlock can't wrap the details slot's `<pre><code>` blocks.
 * Inject the same affordance post-mount instead (shared logic lives in
 * utils/copyButton). The hook must rerun after RawHTML's own innerHTML
 * effect for the same `html` (child effects run first), which re-adding
 * unconditionally plus the per-pre guard covers.
 */
function useDetailsCopyButtons(
  ref: React.RefObject<HTMLDivElement | null>,
  html: string | undefined,
) {
  useEffect(() => {
    const container = ref.current
    if (!container || !html) return

    const cleanups: Array<() => void> = []
    for (const pre of container.querySelectorAll("pre")) {
      if (pre.querySelector(`.${COPY_BUTTON_CLASS}`)) continue

      const button = createCopyButton()
      let cancelFlash: (() => void) | undefined
      const onClick = async () => {
        const text = pre.querySelector("code")?.textContent ?? ""
        await copyTextToClipboard(text)
        cancelFlash?.()
        cancelFlash = flashCopied(button)
      }
      button.addEventListener("click", onClick)
      pre.appendChild(button)
      cleanups.push(() => {
        cancelFlash?.()
        button.removeEventListener("click", onClick)
      })
    }
    return () => cleanups.forEach((cleanup) => cleanup())
  }, [ref, html])
}

/**
 * Whether the details body is exactly one code block (no prose around it).
 * Only then does copy move up into the summary row; mixed content keeps
 * per-block buttons. Runs after RawHTML's own innerHTML effect (child
 * effects run first), so the DOM is populated for either content flavor.
 */
function useSingleCodeBlock(
  ref: React.RefObject<HTMLDivElement | null>,
  content: string | undefined,
): boolean {
  const [single, setSingle] = useState(false)
  useEffect(() => {
    const body = ref.current
    if (!body) {
      setSingle(false)
      return
    }
    const pres = body.querySelectorAll("pre")
    setSingle(
      pres.length === 1 &&
        body.textContent?.trim() === pres[0]!.textContent?.trim(),
    )
  }, [ref, content])
  return single
}

function ToolRequestDetails({
  requestCall,
  showRequest,
  requestCollapsed,
  stopScroll,
}: {
  requestCall: string | undefined
  showRequest: boolean
  requestCollapsed: boolean
  stopScroll: ReturnType<typeof useChatStopScroll>
}): React.ReactNode {
  if (!showRequest || !requestCall) {
    return null
  }

  const requestMarkdown = markdownCodeBlock(requestCall, "")
  // `requestCollapsed` (client policy: image-bearing results) forces the
  // collapsed <details> form even for short calls.
  const isLongRequest = requestCollapsed || requestCall.split("\n").length > 2

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
