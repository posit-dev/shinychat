import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

export type ContentType = "markdown" | "html" | "text"

export type MessagePayload = {
  id?: string
  role: "user" | "assistant"
  content: string
  content_type: ContentType
  icon?: string
  html_deps?: HtmlDep[]
}

export type ChatAction =
  | { type: "message"; message: MessagePayload }
  | { type: "chunk_start"; message: MessagePayload }
  | {
      type: "chunk"
      content: string
      operation: "append" | "replace"
      content_type?: ContentType
    }
  | { type: "chunk_end" }
  | { type: "clear" }
  | {
      type: "update_input"
      value?: string
      placeholder?: string
      submit?: boolean
      focus?: boolean
    }
  | { type: "remove_loading" }
  | { type: "hide_tool_request"; requestId: string }

export type ShinyChatEnvelope = {
  id: string
  action: ChatAction
  html_deps?: HtmlDep[]
}

/** Runtime check that an unknown value has the shape of a ShinyChatEnvelope. */
export function isValidEnvelope(x: unknown): x is ShinyChatEnvelope {
  if (!x || typeof x !== "object") return false
  const obj = x as Record<string, unknown>
  if (typeof obj.id !== "string") return false
  if (!obj.action || typeof obj.action !== "object") return false
  if (typeof (obj.action as Record<string, unknown>).type !== "string")
    return false
  return true
}

export type ShinyClientMessage = {
  message: string
  headline?: string
  status?: "error" | "info" | "warning"
}

/** Core transport: message passing between client and server. */
export interface ChatTransport {
  sendInput(id: string, value: string): void
  onMessage(id: string, callback: (action: ChatAction) => void): () => void
}

/** Shiny-specific lifecycle: DOM binding, dependency rendering, error display. */
export interface ShinyLifecycle {
  renderDependencies(deps: HtmlDep[]): Promise<void>
  bindAll(el: HTMLElement): Promise<void>
  unbindAll(el: HTMLElement): void
  showClientMessage(msg: ShinyClientMessage): void
}
