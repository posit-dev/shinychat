import { ToolRequest } from "./ToolRequest"
import { useChatToolState } from "./context"

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
  const { hiddenToolRequests } = useChatToolState()

  if (!requestId || !toolName) return null
  if (hiddenToolRequests.has(requestId)) return null

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
