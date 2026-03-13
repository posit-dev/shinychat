import { ToolRequest } from "./ToolRequest"

interface ToolRequestBridgeProps {
  "request-id"?: string
  "tool-name"?: string
  "tool-title"?: string
  intent?: string
  arguments?: string
  hidden?: string | boolean
  node?: unknown
  children?: React.ReactNode
}

export function ToolRequestBridge({
  "request-id": requestId,
  "tool-name": toolName,
  "tool-title": toolTitle,
  intent,
  arguments: toolArguments,
}: ToolRequestBridgeProps) {
  if (!requestId || !toolName) return null

  return (
    <div className="shiny-tool-request">
      <ToolRequest
        requestId={requestId}
        toolName={toolName}
        toolTitle={toolTitle}
        intent={intent}
        arguments={toolArguments ?? "{}"}
      />
    </div>
  )
}
