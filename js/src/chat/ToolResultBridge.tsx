import { useContext, useEffect } from "react"
import { ToolResult } from "./ToolResult"
import { ChatDispatchContext } from "./context"

interface ToolResultBridgeProps {
  "request-id"?: string
  "tool-name"?: string
  "tool-title"?: string
  intent?: string
  status?: string
  value?: string
  "value-type"?: string
  "request-call"?: string
  "show-request"?: string | boolean
  "full-screen"?: string | boolean
  expanded?: string | boolean
  footer?: string
  node?: unknown
  children?: React.ReactNode
}

function isTruthy(val: string | boolean | undefined): boolean {
  return val === true || val === "" || val === "true"
}

export function ToolResultBridge({
  "request-id": requestId,
  "tool-name": toolName,
  "tool-title": toolTitle,
  intent,
  status,
  value,
  "value-type": valueType,
  "request-call": requestCall,
  "show-request": showRequest,
  "full-screen": fullScreen,
  expanded,
  footer,
}: ToolResultBridgeProps) {
  const dispatch = useContext(ChatDispatchContext)

  useEffect(() => {
    if (!dispatch || !requestId) return
    // Keep tool-request hiding tied to rendered results, matching Lit behavior.
    dispatch({ type: "hide_tool_request", requestId })
  }, [dispatch, requestId])

  if (!requestId || !toolName) return null

  return (
    <div className="shiny-tool-result">
      <ToolResult
        requestId={requestId}
        toolName={toolName}
        toolTitle={toolTitle}
        intent={intent}
        status={status ?? "success"}
        value={value ?? ""}
        valueType={valueType ?? "markdown"}
        requestCall={requestCall}
        showRequest={isTruthy(showRequest)}
        fullScreen={isTruthy(fullScreen)}
        expanded={isTruthy(expanded)}
        footer={footer}
      />
    </div>
  )
}
