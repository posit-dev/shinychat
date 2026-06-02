import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

export type ContentType = "markdown" | "html" | "text" | "thinking"

export interface GreetingOptions {
  dismissible?: boolean
}

export type MessagePayloadSegment = {
  content: string
  content_type: ContentType
}

export interface SlashCommandDef {
  name: string
  description: string
  /**
   * Whether invoking the command participates in the conversation: adds the
   * `/cmd args` user message and shows a pending/loading state. False means a
   * pure side effect (nothing added to the transcript, no loading).
   */
  echo: boolean
}

/** Detail payload of the cancelable `shiny:chat-slash-command` DOM event. */
export interface SlashCommandEventDetail {
  /** The chat container element id (use to target a specific chat instance). */
  readonly id: string
  /** The parsed command name (read-only). */
  readonly command: string
  /** The parsed argument text after the command name (read-only). */
  readonly args: string
  /**
   * Effective echo for this invocation. This is the one field a listener may
   * mutate (e.g. `e.detail.echo = true`) to change whether the command is shown
   * as a user message; `command`/`args` are informational and not honored if mutated.
   */
  echo: boolean
}

export type MessagePayload = {
  id?: string
  role: "user" | "assistant"
  icon?: string
  segments: MessagePayloadSegment[]
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
  | { type: "clear"; greeting?: boolean }
  | {
      type: "update_input"
      value?: string
      placeholder?: string
      submit?: boolean
      focus?: boolean
    }
  | { type: "remove_loading" }
  | { type: "update_cancel"; enable_cancel: boolean }
  | { type: "hide_tool_request"; requestId: string }
  | {
      type: "greeting"
      content: string
      content_type: ContentType
      options: GreetingOptions
    }
  | {
      type: "greeting_start"
      content: string
      content_type: ContentType
      options: GreetingOptions
    }
  | {
      type: "greeting_chunk"
      content: string
      operation: "append" | "replace"
      content_type?: ContentType
    }
  | { type: "greeting_end" }
  | { type: "greeting_clear" }
  | { type: "update_slash_commands"; commands: SlashCommandDef[] }

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
  sendCancel(id: string): void
  sendSlashCommand(
    id: string,
    command: string,
    args: string,
    echo: boolean,
  ): void
  onMessage(id: string, callback: (action: ChatAction) => void): () => void
}

/** Shiny-specific lifecycle: DOM binding, dependency rendering, error display. */
export interface ShinyLifecycle {
  renderDependencies(deps: HtmlDep[]): Promise<void>
  bindAll(el: HTMLElement): Promise<void>
  unbindAll(el: HTMLElement): void
  showClientMessage(msg: ShinyClientMessage): void
}
