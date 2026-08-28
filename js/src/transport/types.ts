import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"
import type { AttachmentPayload } from "../chat/attachments"
import type { SnapshotMessage } from "../chat/state"

export type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

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

/** Per-call grouping override; mirrors `ToolGrouping` in chat/tool-model.ts. */
export type StructuredBlockGrouping = "none" | "tool" | "all"

/**
 * A typed, server-authored tool request envelope. The envelope itself is the
 * trust signal: only the server can construct these blocks, so trusted-HTML
 * fields (`title`, `icon`) render through the shared RawHTML sink while text
 * fields are escaped. The client derives a `running` call from an unpaired
 * request (a request with no result of the same `request_id` yet).
 */
export type ToolRequestBlock = {
  type: "tool_request"
  version: 1
  /** Correlates with the result; keys transcript-wide request suppression. */
  request_id: string
  tool_name: string
  /** HTML → RawHTML (the tool definition's title; was tool-title/definitionTitle) */
  title?: string
  /** HTML → RawHTML (the tool definition's icon; was definitionIcon) */
  icon?: string
  /** text → escaped */
  intent?: string
  /** JSON string, rendered as a markdown code block (escaped) */
  arguments?: string
  grouping?: StructuredBlockGrouping
}

/**
 * A typed, server-authored tool result envelope. The envelope itself is the
 * trust signal: only the server can construct these blocks, so trusted-HTML
 * fields (`value` with `value_type: "html"`, `title`, `icon`, `footer`)
 * render through the shared RawHTML sink while text fields are escaped.
 */
export type ToolResultBlock = {
  type: "tool_result"
  version: 1
  /** Correlates with the request; keys transcript-wide request suppression. */
  request_id: string
  tool_name: string
  /** "running" is NOT a wire value; the client derives it from an unpaired request. */
  status: "success" | "error"
  value?: string
  value_type?: "html" | "markdown" | "text" | "code" | "content_extra"
  request_call?: string
  /** HTML → RawHTML */
  title?: string
  /** HTML → RawHTML */
  icon?: string
  /** text → escaped */
  intent?: string
  /** text → escaped */
  label?: string
  /** text → escaped */
  value_preview?: string
  grouping?: StructuredBlockGrouping
  show_request?: boolean
  expanded?: boolean
  open_style?: "minimal" | "framed"
  full_screen?: boolean
  /** Internal-only: set by wrap_custom_tool_result, never author-facing. */
  custom_display?: boolean
  /** HTML → RawHTML */
  footer?: string
}

/**
 * One source in a `web_search_results` block: a real JSON array entry, not a
 * stringified attribute. `url` is required; `title`/`domain` are display
 * hints (the client derives a domain from the URL when absent).
 */
export type WebSearchSource = {
  url: string
  title?: string
  domain?: string
}

/**
 * A typed, server-authored web-search envelope. The envelope itself is the
 * trust signal: only the server can construct these blocks. Consecutive
 * web_* blocks group client-side into one `web_activity` block on arrival.
 */
export type WebSearchBlock = {
  type: "web_search"
  version: 1
  query: string
  /**
   * Answer-citation fallback (the structured re-expression of
   * rehypeAttachCitedSources): sources the answer cited, shown only while
   * no provider results attach to this search.
   */
  cited_sources?: WebSearchSource[]
}

/**
 * The results paired with a preceding `web_search`: the client attaches the
 * sources to the earliest still-pending search in the activity (the
 * adjacency pairing `WebActivity.parseItems` uses on the markup path).
 */
export type WebSearchResultsBlock = {
  type: "web_search_results"
  version: 1
  sources: WebSearchSource[]
}

/** A typed, server-authored web-fetch envelope. */
export type WebFetchBlock = {
  type: "web_fetch"
  version: 1
  url: string
  /** Absent when the server didn't report one (chatlas allows None). */
  status?: "success" | "error"
}

/**
 * A typed, server-authored raw-HTML island — the structured re-expression of
 * the `<shiny-chat-raw-html>` islands a string `html` segment carries. The
 * envelope itself is the trust signal: only the server can construct these
 * blocks, so `content` renders through the shared RawHTML sink. The block is
 * opaque to the thinking-tag/fence state machine, which operates only on
 * string content.
 */
export type HtmlBlock = {
  type: "html_block"
  version: 1
  /** Trusted HTML → RawHTML */
  content: string
  /**
   * Dependencies this island needs, rendered before its HTML mounts (the
   * block-level complement to the envelope's `html_deps`).
   */
  html_deps?: HtmlDep[]
}

/**
 * Server-authored structured blocks carried in `MessagePayload.segments`
 * (outside a stream) or via a `block_insert` action (mid-stream). The union
 * grows per the design.
 */
export type StructuredBlock =
  | ToolRequestBlock
  | ToolResultBlock
  | WebSearchBlock
  | WebSearchResultsBlock
  | WebFetchBlock
  | HtmlBlock

/**
 * One entry of `MessagePayload.segments`: a string segment
 * (`{content, content_type}`) or a structured block (discriminated by the
 * presence of `type`).
 */
export type SegmentPayload = MessagePayloadSegment | StructuredBlock

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
  segments: SegmentPayload[]
  attachments?: AttachmentPayload[]
  siblings?: { index: number; total: number }
}

/**
 * Fields shared by drawer content mutations. Omitted fields retain their
 * prior value; an empty string explicitly clears content or title.
 */
export type DrawerMutationPayload = {
  content?: string
  title?: string
  /** Dependencies accompanying replacement content. */
  html_deps?: HtmlDep[]
}

export type ChatAction =
  | { type: "message"; message: MessagePayload; html_deps?: HtmlDep[] }
  | { type: "chunk_start"; message: MessagePayload; html_deps?: HtmlDep[] }
  | {
      type: "chunk"
      content: string
      operation: "append" | "replace"
      content_type?: ContentType
      html_deps?: HtmlDep[]
    }
  | { type: "chunk_end" }
  | {
      /**
       * Delivers one complete structured block while a message stream is in
       * flight. Appends to `streamingMessage.blocks`; a no-op (with a
       * console.warn) when no stream is in flight. Never affects the
       * thinking-tag/fence state machine, which operates only on strings.
       */
      type: "block_insert"
      block: StructuredBlock
      html_deps?: HtmlDep[]
    }
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
  | ({ type: "drawer_show" } & DrawerMutationPayload)
  | { type: "drawer_hide" }
  | { type: "drawer_toggle" }
  | ({ type: "drawer_update" } & DrawerMutationPayload)
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
      /** Used by bookmark-mode switches, where a soft URL update isn't sufficient. */
      reload?: boolean
    }
  | {
      type: "update_siblings"
      data: Record<number, { index: number; total: number }>
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
  /** Report the client's settled-message snapshot (regular-priority input). */
  sendMessagesSnapshot(id: string, snapshot: SnapshotMessage[]): void
  onMessage(id: string, callback: (action: ChatAction) => void): () => void
  sendHistorySelect(id: string, convId: string): void
  sendHistoryNew(id: string): void
  sendHistoryRename(id: string, convId: string, title: string): void
  sendHistoryDelete(id: string, convId: string): void
  sendMessageEdit(
    id: string,
    index: number,
    content: string,
    attachments?: AttachmentPayload[],
  ): void
  sendMessageNavigate(
    id: string,
    index: number,
    direction: "prev" | "next",
  ): void
}

/** Shiny-specific lifecycle: DOM binding, dependency rendering, error display. */
export interface ShinyLifecycle {
  renderDependencies(deps: HtmlDep[]): Promise<void>
  bindAll(el: HTMLElement): Promise<void>
  unbindAll(el: HTMLElement): void
  showClientMessage(msg: ShinyClientMessage): void
}
