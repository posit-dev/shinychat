import { memo, useRef } from "react"
import { ToolCard } from "./ToolCard"
import { RawHTML } from "./RawHTML"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"
import { exclamationCircleFill, filePdfFill } from "../utils/icons"
import { useFullscreen } from "./useFullscreen"

interface ContentExtraItem {
  type: "image" | "pdf" | "text"
  src?: string
  filename?: string
  value?: string
  value_type?: "html" | "markdown" | "text" | "code"
}

function PdfBadge({ filename }: { filename: string }) {
  return (
    <div className="shinychat-pdf badge fs-6 text-bg-secondary">
      <span
        className="shinychat-pdf__icon me-1"
        dangerouslySetInnerHTML={{ __html: filePdfFill }}
      />
      <span className="shinychat-pdf__filename font-monospace">{filename}</span>
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
      content={markdownCodeBlock(value, "text")}
      contentType="markdown"
      streaming={false}
    />
  )
}

export interface ToolResultProps {
  requestId: string
  toolName: string
  toolTitle?: string
  intent?: string
  status: string
  value: string
  valueType: string
  requestCall?: string
  showRequest?: boolean
  fullScreen?: boolean
  expanded?: boolean
  icon?: string
  footer?: string
}

export const ToolResult = memo(function ToolResult({
  requestId,
  toolName,
  toolTitle,
  intent,
  status,
  value,
  valueType,
  requestCall,
  showRequest = false,
  fullScreen = false,
  expanded = false,
  icon: iconProp,
  footer,
}: ToolResultProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const { enterFullscreen, overlay } = useFullscreen(cardRef)

  const isError = status === "error"
  const classStatus = isError ? "text-danger" : ""
  const icon = isError ? exclamationCircleFill : iconProp
  const titleTemplate = isError ? "{title} failed" : "{title}"

  return (
    <>
      <ToolCard
        requestId={requestId}
        toolName={toolName}
        toolTitle={toolTitle}
        intent={intent}
        icon={icon}
        classStatus={classStatus}
        titleTemplate={titleTemplate}
        fullScreen={fullScreen}
        initialExpanded={expanded}
        footer={footer}
        onEnterFullscreen={enterFullscreen}
        cardRef={cardRef}
      >
        {renderRequest(requestCall, showRequest)}
        {renderResult(value, valueType, showRequest)}
      </ToolCard>
      {overlay}
    </>
  )
})

function renderRequest(
  requestCall: string | undefined,
  showRequest: boolean,
): React.ReactNode {
  if (!showRequest || !requestCall) {
    return null
  }

  const requestMarkdown = markdownCodeBlock(requestCall, "")
  const isLongRequest = requestCall.split("\n").length > 2

  return (
    <div className="shiny-tool-result__request">
      {isLongRequest ? (
        <details>
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

function renderResult(
  value: string,
  valueType: string,
  showRequest: boolean,
): React.ReactNode {
  const displayValue = value || "[Empty result]"

  let resultContent: React.ReactNode

  if (valueType === "html") {
    resultContent = <RawHTML html={displayValue} />
  } else if (valueType === "text") {
    resultContent = <p>{displayValue}</p>
  } else if (valueType === "content_extra") {
    try {
      const items = JSON.parse(value) as ContentExtraItem[]
      resultContent = (
        <div className="shinychat-content-extra">
          {items.map((item, i) => {
            if (item.type === "image") {
              return (
                <img key={i} src={item.src} className="shinychat-tool-image" />
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
