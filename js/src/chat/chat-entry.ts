import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import type { InitialGreeting } from "./ChatApp"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ChatMessageData } from "./state"
import type { ContentType, GreetingOptions } from "../transport/types"
import { uuid } from "../utils/uuid"
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
      token = crypto.randomUUID()
      window.localStorage.setItem(BROWSER_TOKEN_KEY, token)
    }
    return token
  } catch {
    // localStorage unavailable (private mode, sandboxed iframe, etc.)
    if (!fallbackBrowserToken) {
      fallbackBrowserToken = crypto.randomUUID()
    }
    return fallbackBrowserToken
  }
}

const CHAT_INPUT_TAG = "shiny-chat-input"
const CHAT_MESSAGE_TAG = "shiny-chat-message"
const CHAT_FOOTER_TAG = "shiny-chat-footer"

function parseInitialMessages(container: HTMLElement): ChatMessageData[] {
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

class ChatContainerElement extends HTMLElement {
  private reactRoot: Root | null = null
  private footerEl: Element | null = null
  private pendingUnmount: ReturnType<typeof setTimeout> | null = null

  connectedCallback() {
    // Moving the element in the DOM fires disconnectedCallback then
    // connectedCallback synchronously in the same tick. The deferred unmount
    // scheduled on disconnect hasn't run yet, so cancel it here to keep the
    // live React root (and its rendered conversation) intact across the move.
    if (this.pendingUnmount !== null) {
      clearTimeout(this.pendingUnmount)
      this.pendingUnmount = null
    }

    if (this.reactRoot) return

    const elementId = this.getAttribute("id") ?? ""
    const iconAssistant = this.getAttribute("icon-assistant") ?? undefined
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

    const initialMessages = parseInitialMessages(this)

    if (!this.footerEl) {
      this.footerEl = this.querySelector(CHAT_FOOTER_TAG)
      // Detach from the DOM before React takes over this container.
      // RawDOM later adopts the children, preserving their DOM state.
      this.footerEl?.remove()
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

    this.reactRoot = createRoot(this)
    this.reactRoot.render(
      createElement(ChatApp, {
        transport,
        shinyLifecycle: transport,
        elementId,
        iconAssistant,
        inputId,
        cancelId,
        uploadAccept,
        maxUploadSize,
        placeholder,
        initialMessages,
        initialGreeting,
        enableCancel,
        enableUpload,
        footerEl: this.footerEl ?? undefined,
        slashCommandId,
        submitKey,
      }),
    )
  }

  disconnectedCallback() {
    // Defer teardown so a move (disconnect immediately followed by reconnect)
    // can cancel it. If the element is genuinely removed, no reconnect cancels
    // the timer and cleanup runs on the next tick.
    this.pendingUnmount = setTimeout(() => {
      transport.unbindAll(this)
      this.reactRoot?.unmount()
      this.reactRoot = null
      this.pendingUnmount = null
    }, 0)
  }
}

if (!customElements.get("shiny-chat-container")) {
  customElements.define("shiny-chat-container", ChatContainerElement)
}
