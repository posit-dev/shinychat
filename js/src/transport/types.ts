import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

export type ContentType = "markdown" | "html" | "text" | "semi-markdown"

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

export type ShinyChatEnvelope = {
  id: string
  action: ChatAction
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
