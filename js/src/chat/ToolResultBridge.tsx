import { ToolResult } from "./ToolResult"

interface ToolResultBridgeProps {
  "request-id"?: string
  "tool-name"?: string
  "tool-title"?: string
  label?: string
  intent?: string
  status?: string
  value?: string
  "value-type"?: string
  "request-call"?: string
  "show-request"?: string | boolean
  "full-screen"?: string | boolean
  expanded?: string | boolean
  icon?: string
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
  label,
  intent,
  status,
  value,
  "value-type": valueType,
  "request-call": requestCall,
  "show-request": showRequest,
  "full-screen": fullScreen,
  expanded,
  icon,
  footer,
}: ToolResultBridgeProps) {
  // No longer announces that it supersedes its request: ChatApp derives that
  // from the same content this bridge renders (`supersededRequestIds`), under
  // the same gates the router uses. Announcing it here could only disagree.
  if (!requestId || !toolName) return null

  return (
    <div className="shiny-tool-result">
      <ToolResult
        toolName={toolName}
        toolTitle={toolTitle}
        label={label}
        intent={intent}
        status={status ?? "success"}
        value={value ?? ""}
        valueType={valueType ?? "markdown"}
        requestCall={requestCall}
        showRequest={isTruthy(showRequest)}
        fullScreen={isTruthy(fullScreen)}
        expanded={isTruthy(expanded)}
        icon={icon}
        footer={footer}
      />
    </div>
  )
}
