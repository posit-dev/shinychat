import { useEffect } from "react"
import { ToolCard } from "./ToolCard"
import { useChatDispatch } from "./context"
import { MarkdownContent } from "../markdown/MarkdownContent"
import { markdownCodeBlock } from "../markdown/markdownCodeBlock"
import { exclamationCircleFill } from "../utils/icons"

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
}

/**
 * Displays the result of a tool execution.
 * On mount, dispatches `HIDE_TOOL_REQUEST` to hide the corresponding request.
 * Ports `ShinyToolResult` from the Lit implementation.
 */
export function ToolResult({
  requestId,
  toolName,
  toolTitle,
  intent,
  status,
  value,
  valueType,
  requestCall,
  showRequest = false,
}: ToolResultProps) {
  const dispatch = useChatDispatch()

  // On mount, hide the corresponding tool request
  useEffect(() => {
    dispatch({ type: "HIDE_TOOL_REQUEST", requestId })
  }, [requestId, dispatch])

  const isError = status === "error"
  const classStatus = isError ? "text-danger" : ""
  const icon = isError ? exclamationCircleFill : undefined
  const titleTemplate = isError ? "{title} failed" : "{title}"

  return (
    <ToolCard
      requestId={requestId}
      toolName={toolName}
      toolTitle={toolTitle}
      intent={intent}
      icon={icon}
      classStatus={classStatus}
      titleTemplate={titleTemplate}
    >
      {renderRequest(requestCall, showRequest)}
      {renderResult(value, valueType, showRequest)}
    </ToolCard>
  )
}

/**
 * Renders the tool request call, if applicable.
 * If the request call is long (> 2 lines), it is wrapped in a `<details>` element.
 */
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

/**
 * Renders the tool result content according to the `valueType`.
 */
function renderResult(
  value: string,
  valueType: string,
  showRequest: boolean,
): React.ReactNode {
  const displayValue = value || "[Empty result]"

  let resultContent: React.ReactNode

  if (valueType === "html") {
    resultContent = <div dangerouslySetInnerHTML={{ __html: displayValue }} />
  } else if (valueType === "text") {
    resultContent = <p>{displayValue}</p>
  } else {
    // markdown, code, or default
    const markdownContent =
      valueType !== "markdown"
        ? markdownCodeBlock(displayValue, "text") // "code" type wraps as code block
        : displayValue

    resultContent = (
      <MarkdownContent
        content={markdownContent}
        contentType="markdown"
        streaming={false}
      />
    )
  }

  // If not showing the request and result is raw HTML, return unwrapped
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
