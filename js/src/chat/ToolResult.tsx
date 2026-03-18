import { memo, useRef } from "react"
import { ToolCard } from "./ToolCard"
import { RawHTML } from "./RawHTML"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"
import { exclamationCircleFill } from "../utils/icons"
import { useFullscreen } from "./useFullscreen"

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
