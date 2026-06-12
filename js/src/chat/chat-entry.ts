import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import type { InitialGreeting } from "./ChatApp"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ChatMessageData } from "./state"
import type { ContentType, GreetingOptions } from "../transport/types"
import { uuid } from "../utils/uuid"

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

    const inputEl = this.querySelector(CHAT_INPUT_TAG)
    const placeholder = inputEl?.getAttribute("placeholder") ?? undefined

    // Falls back to "<elementId>_user_input" (the R package's convention)
    const inputId = inputEl?.getAttribute("id") ?? `${elementId}_user_input`
    const cancelId = `${elementId}_cancel`

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

    // Send the browser token once per element so the server can correlate this
    // client across sessions. No event priority — the server reads it with
    // req() as a persistent value. A genuine remove + re-attach re-sends the
    // token, which is harmless because the value is identical and Shiny
    // overwrites in place.
    //
    // shinychat.js loads as a <script type="module"> (deferred), so
    // connectedCallback fires after HTML parsing but potentially before Shiny's
    // own jQuery ready handler has run. Deferring via initializedPromise.then()
    // handles both orderings:
    //   • page-load case: promise is pending → callback fires once Shiny inits
    //   • dynamic-insertion case: promise is already resolved → callback fires
    //     on the next microtask
    window.Shiny?.initializedPromise.then(() => {
      window.Shiny?.setInputValue?.(
        `${elementId}_history_browser_token`,
        getBrowserToken(),
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
        placeholder,
        initialMessages,
        initialGreeting,
        enableCancel,
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
