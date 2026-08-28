import { ToolResult } from "./ToolResult"
import { isTruthyAttribute } from "./tool-protocol"

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
  "custom-display"?: string | boolean
  icon?: string
  footer?: string
  node?: unknown
  children?: React.ReactNode
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
  "custom-display": customDisplay,
  icon,
  footer,
}: ToolResultBridgeProps) {
  // Complete tool elements travel as structured blocks, not markup. This
  // bridge is fallback-only for tool markup in html-typed string content
  // (e.g. legacy emitters), so a custom payload must wait for that path
  // rather than becoming a subtly incorrect ordinary card.
  if (isTruthyAttribute(customDisplay)) return null

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
        showRequest={isTruthyAttribute(showRequest)}
        fullScreen={isTruthyAttribute(fullScreen)}
        expanded={isTruthyAttribute(expanded)}
        icon={icon}
        footer={footer}
      />
    </div>
  )
}
