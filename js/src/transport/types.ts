import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"
import type { AttachmentPayload } from "../chat/attachments"

export type ContentType = "markdown" | "html" | "text" | "thinking"

export interface ConversationMeta {
  id: string
  title: string
  // ISO 8601 strings — matches Python model serialization
  created_at: string
  updated_at: string
}

export interface GreetingOptions {
  persistent?: boolean
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
  /** The chat id (use to target a specific chat instance). */
  readonly id: string
  /** The parsed command name (read-only). */
  readonly command: string
  /** The parsed user text after the command name (read-only). */
  readonly userText: string
  /**
   * Effective echo for this invocation. This is the one field a listener may
   * mutate (e.g. `e.detail.echo = true`) to change whether the command is shown
   * as a user message; `command`/`userText` are informational and not honored if mutated.
   */
  echo: boolean
}

export type MessagePayload = {
  id?: string
  role: "user" | "assistant"
  icon?: string
  segments: MessagePayloadSegment[]
  attachments?: AttachmentPayload[]
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
      attachments?: AttachmentPayload[]
      attachment_mode?: "append" | "set"
    }
  | { type: "remove_loading" }
  | { type: "update_cancel"; enable_cancel: boolean }
  | { type: "update_upload"; enable_upload: boolean }
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
  | {
      type: "history_update"
      enabled: boolean
      conversations: ConversationMeta[]
      active_id: string | null
    }
  | {
      type: "history_navigate"
      /** Query string to push via history.replaceState, e.g. "?conv=<id>". Null clears the query. */
      url: string | null
      /** Conversation to record as current in localStorage (null on New chat). */
      active_id: string | null
      /** Force a hard navigation (full reload), used by bookmark-mode switches. */
      reload?: boolean
    }

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

/** The user's submission: text plus any attachments, sent as one input value. */
export type UserInputValue = {
  text: string
  attachments: AttachmentPayload[]
}

/** Core transport: message passing between client and server. */
export interface ChatTransport {
  /**
   * Send the user's submission as the type-tagged `shinychat.userInput` value
   * for the given input id (read server-side as `input$<id>`). The shape
   * signals the upload mode: a bare `string` when the attachment affordance is
   * disabled (back-compatible with the historical string-valued input), or a
   * `{text, attachments}` composite when it is enabled.
   */
  sendInput(id: string, value: string | UserInputValue): void
  sendCancel(id: string): void
  sendSlashCommand(
    id: string,
    command: string,
    userText: string,
    echo: boolean,
  ): void
  onMessage(id: string, callback: (action: ChatAction) => void): () => void
  sendHistorySelect(id: string, convId: string): void
  sendHistoryNew(id: string): void
  sendHistoryRename(id: string, convId: string, title: string): void
  sendHistoryDelete(id: string, convId: string): void
}

/** Shiny-specific lifecycle: DOM binding, dependency rendering, error display. */
export interface ShinyLifecycle {
  renderDependencies(deps: HtmlDep[]): Promise<void>
  bindAll(el: HTMLElement): Promise<void>
  unbindAll(el: HTMLElement): void
  showClientMessage(msg: ShinyClientMessage): void
}
