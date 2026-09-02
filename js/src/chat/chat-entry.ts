import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import type { ChatAppProps, InitialGreeting } from "./ChatApp"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ChatDrawerState, ChatMessageData, ToolGrouping } from "./state"
import { messagePayloadToData } from "./state"
import type {
  ContentType,
  GreetingOptions,
  MessagePayload,
} from "../transport/types"
import { uuid } from "../utils/uuid"
import { parseJsonArray } from "../utils/json"
import { DeferredTeardown } from "../utils/deferredTeardown"
import { DEFAULT_UPLOAD_ACCEPT } from "./attachments"
import {
  getCurrentConversationId,
  getConversationIdFromUrl,
} from "./currentConversation"

// Single shared transport instance for all chat instances on the page
const transport = getShinyTransport()

const BROWSER_TOKEN_KEY = "shinychat-browser-token"

// Cached fallback token for private-browsing mode (localStorage unavailable).
// All chat elements on the page share the same per-session token.
let fallbackBrowserToken: string | null = null

function getBrowserToken(): string {
  try {
    let token = window.localStorage.getItem(BROWSER_TOKEN_KEY)
    if (!token) {
      token = uuid()
      window.localStorage.setItem(BROWSER_TOKEN_KEY, token)
    }
    return token
  } catch {
    // localStorage unavailable (private mode, sandboxed iframe, etc.)
    if (!fallbackBrowserToken) {
      fallbackBrowserToken = uuid()
    }
    return fallbackBrowserToken
  }
}

const CHAT_INPUT_TAG = "shiny-chat-input"
const CHAT_MESSAGE_TAG = "shiny-chat-message"
const CHAT_TOOLBAR_TAG = "shiny-chat-input-toolbar"
const CHAT_FOOTER_TAG = "shiny-chat-footer"
const CHAT_DRAWER_TAG = "shiny-chat-drawer"

/**
 * Parse the `data-initial-messages` attribute: a JSON array of message
 * payloads the server embeds when any initial message carries structured
 * blocks. Each entry replays through `messagePayloadToData()`. Returns null
 * when malformed so the caller can fall back to static tags.
 */
function parseInitialMessagesAttr(
  raw: string,
  toolGrouping?: ToolGrouping,
): ChatMessageData[] | null {
  const parsed = parseJsonArray(raw, "data-initial-messages attribute")
  if (parsed === null) return null

  const messages: ChatMessageData[] = []
  for (const entry of parsed) {
    if (
      typeof entry !== "object" ||
      entry === null ||
      !Array.isArray((entry as { segments?: unknown }).segments)
    ) {
      console.warn(
        "Skipping malformed entry in data-initial-messages: expected an object with a segments array",
      )
      continue
    }
    messages.push(messagePayloadToData(entry as MessagePayload, toolGrouping))
  }
  return messages
}

function parseInitialMessages(
  container: HTMLElement,
  toolGrouping?: ToolGrouping,
): ChatMessageData[] {
  // When the server embeds initial messages as JSON (any message carries
  // structured blocks), the attribute is authoritative and no static
  // <shiny-chat-message> tags are emitted.
  const attr = container.getAttribute("data-initial-messages")
  if (attr !== null) {
    const messages = parseInitialMessagesAttr(attr, toolGrouping)
    if (messages) return messages
    // Malformed payload: fall through to the static-tag path.
  }

  const messageEls = container.querySelectorAll(CHAT_MESSAGE_TAG)
  const messages: ChatMessageData[] = []

  messageEls.forEach((el) => {
    const content = el.getAttribute("content") ?? ""
    const role =
      (el.getAttribute("data-role") as "user" | "assistant") ?? "assistant"
    const contentType =
      (el.getAttribute("content-type") as ContentType) ?? "markdown"
    const icon = el.getAttribute("icon") ?? undefined

    messages.push({
      id: uuid(),
      role,
      content,
      streaming: false,
      icon,
      blocks: [{ type: "content", content, contentType }],
    })
  })

  return messages
}

function parseInitialGreeting(
  container: HTMLElement,
): InitialGreeting | undefined {
  const raw = container.getAttribute("greeting")
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw) as {
      content?: string
      content_type?: string
      options?: GreetingOptions
    }
    if (!parsed.content) return undefined
    return {
      content: parsed.content,
      contentType: (parsed.content_type as ContentType) ?? "markdown",
      options: parsed.options ?? {},
    }
  } catch {
    return undefined
  }
}

function parseInitialDrawer(
  container: HTMLElement,
): { state: ChatDrawerState; source: Element } | undefined {
  const source = container.querySelector(CHAT_DRAWER_TAG)
  if (!source) return undefined

  const title = source.getAttribute("title")
  return {
    state: {
      enabled: true,
      visible:
        source.hasAttribute("open") &&
        source.getAttribute("open")?.toLowerCase() !== "false",
      title: title || null,
      // The original source element retains initial dependency nodes and is
      // adopted by ChatDrawer on first render, rather than serialized.
      content: source.innerHTML,
      htmlDeps: [],
      width: source.getAttribute("width") || "400px",
      resizable: source.getAttribute("resizable")?.toLowerCase() !== "false",
    },
    source,
  }
}

// `tool-grouping` is an enum, not a tri-state: a recognized value wins, and
// anything else (including absent) defers to the client default in ChatApp.
function parseToolGrouping(value: string | null): ToolGrouping | undefined {
  return value === "none" || value === "tool" || value === "all"
    ? value
    : undefined
}

class ChatContainerElement extends HTMLElement {
  private reactRoot: Root | null = null
  private toolbarEl: Element | null = null
  private footerEl: Element | null = null
  private drawerEl: Element | null = null
  private deferredTeardown = new DeferredTeardown()
  // Retained so an observed attribute can re-render with one field replaced
  // instead of rebuilding every prop (and re-parsing the initial messages,
  // which by then have been superseded by live reducer state).
  private appProps: ChatAppProps | null = null

  static observedAttributes = ["tool-grouping", "show-history"]

  connectedCallback() {
    this.deferredTeardown.cancel()

    if (this.reactRoot) return

    const elementId = this.getAttribute("id") ?? ""
    const iconAssistant = this.getAttribute("icon-assistant") ?? undefined
    const iconSend = this.getAttribute("icon-send") ?? undefined
    const asideFavicon = this.getAttribute("aside-favicon") !== "false"
    // Any present value other than "false" counts as enabled, which keeps the
    // R package's bare `enable-cancel` boolean attribute working. Absent (null)
    // defers the choice to the server (`client=`) via `update_cancel`.
    const enableCancelAttr = this.getAttribute("enable-cancel")
    const enableCancel =
      enableCancelAttr === null ? undefined : enableCancelAttr !== "false"

    // `allow-attachments`: absent (null) defers to the server (`client=`) via
    // `update_upload`; "true"/"false" is an explicit choice.
    const enableUploadAttr = this.getAttribute("allow-attachments")
    const enableUpload =
      enableUploadAttr === null ? undefined : enableUploadAttr !== "false"

    const toolGrouping = parseToolGrouping(this.getAttribute("tool-grouping"))
    const showHistory = this.getAttribute("show-history") !== "false"

    const inputEl = this.querySelector(CHAT_INPUT_TAG)
    const placeholder = inputEl?.getAttribute("placeholder") ?? undefined

    // Falls back to "<elementId>_user_input" (the R package's convention)
    const inputId = inputEl?.getAttribute("id") ?? `${elementId}_user_input`
    const cancelId = `${elementId}_cancel`

    const uploadAcceptAttr = this.getAttribute("attachment-accept")
    const uploadAccept = uploadAcceptAttr
      ? uploadAcceptAttr.split(",").map((s) => s.trim())
      : DEFAULT_UPLOAD_ACCEPT

    // The server always sets max-attachment-size on this element; null means
    // the attribute is absent (e.g. standalone use) and no cap is enforced.
    const maxUploadSizeAttr = this.getAttribute("max-attachment-size")
    const parsedMax = maxUploadSizeAttr ? parseInt(maxUploadSizeAttr, 10) : NaN
    const maxUploadSize: number | null = Number.isFinite(parsedMax)
      ? parsedMax
      : null

    const initialMessages = parseInitialMessages(this, toolGrouping)
    const initialDrawer = parseInitialDrawer(this)

    if (!this.toolbarEl) {
      this.toolbarEl = this.querySelector(CHAT_TOOLBAR_TAG)
    }
    if (!this.footerEl) {
      this.footerEl = this.querySelector(CHAT_FOOTER_TAG)
    }
    if (!this.drawerEl && initialDrawer) {
      this.drawerEl = initialDrawer.source
    }

    const initialGreeting = parseInitialGreeting(this)

    const submitKeyAttr = this.getAttribute("submit-key")
    const submitKey =
      submitKeyAttr === "enter+modifier" ? "enter+modifier" : "enter"

    const slashCommandId = `${elementId}_slash_command`

    // Unbind any Shiny inputs/outputs in the server-rendered content before
    // React replaces the DOM. Without this, Shiny's internal binding registry
    // retains stale references, preventing re-binding of the new React-rendered
    // elements (Shiny thinks the inputs are already bound by ID).
    transport.unbindAll(this)
    // Detach preserved DOM only after unbinding its server-owned subtree.
    // RawDOM and ChatDrawer later adopt those children without serializing.
    this.toolbarEl?.remove()
    this.footerEl?.remove()
    this.drawerEl?.remove()

    // Send the browser token once per element so the server can correlate
    // this client across sessions. The server reads it with req() as a
    // persistent value, so a remove+re-attach resending the same token is
    // harmless — Shiny just overwrites in place.
    //
    // shinychat.js loads as a deferred <script type="module">, so
    // connectedCallback can fire before Shiny's own init has run.
    // initializedPromise.then() handles both orderings (pending vs. already
    // resolved) with the same callback.
    //
    // These use the DOM id (namespaced in modules) to match the server's
    // resolved self.id — unlike slash-command DOM events, which use
    // effective-id.
    window.Shiny?.initializedPromise.then(() => {
      window.Shiny?.setInputValue?.(
        `${elementId}_history_browser_token`,
        getBrowserToken(),
      )
      window.Shiny?.setInputValue?.(
        `${elementId}_history_current_id`,
        getCurrentConversationId(elementId) ?? "",
      )
      window.Shiny?.setInputValue?.(
        `${elementId}_history_url_id`,
        getConversationIdFromUrl() ?? "",
      )
    })

    this.appProps = {
      transport,
      shinyLifecycle: transport,
      elementId,
      iconAssistant,
      iconSend,
      inputId,
      cancelId,
      uploadAccept,
      maxUploadSize,
      placeholder,
      initialMessages,
      initialGreeting,
      initialDrawer: initialDrawer?.state,
      drawerSource: this.drawerEl ?? undefined,
      enableCancel,
      enableUpload,
      asideFavicon,
      showHistory,
      toolGrouping,
      toolbarEl: this.toolbarEl ?? undefined,
      footerEl: this.footerEl ?? undefined,
      slashCommandId,
      submitKey,
    }
    this.reactRoot = createRoot(this)
    this.reactRoot.render(createElement(ChatApp, this.appProps))
  }

  // These display settings update in place rather than rebuilding the chat.
  // Attribute changes before connect are picked up by connectedCallback's own
  // read, hence the guard rather than a queue.
  attributeChangedCallback(
    name: string,
    _old: string | null,
    next: string | null,
  ) {
    if (!this.reactRoot || !this.appProps) return
    if (name === "tool-grouping") {
      this.appProps = {
        ...this.appProps,
        toolGrouping: parseToolGrouping(next),
      }
    } else if (name === "show-history") {
      this.appProps = { ...this.appProps, showHistory: next !== "false" }
    } else {
      return
    }
    this.reactRoot.render(createElement(ChatApp, this.appProps))
  }

  disconnectedCallback() {
    this.deferredTeardown.schedule(() => {
      transport.unbindAll(this)
      this.reactRoot?.unmount()
      this.reactRoot = null
    })
  }
}

if (!customElements.get("shiny-chat-container")) {
  customElements.define("shiny-chat-container", ChatContainerElement)
}
