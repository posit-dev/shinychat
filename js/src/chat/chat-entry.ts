import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ChatMessageData } from "./state"
import type { ContentType } from "../transport/types"

// Import chat-tools.ts to register shiny-tool-request and shiny-tool-result
// custom elements (Lit-based implementation still used for these)
import "./chat-tools"

// Single shared transport instance for all chat instances on the page
const transport = getShinyTransport()

const CHAT_INPUT_TAG = "shiny-chat-input"
const CHAT_MESSAGE_TAG = "shiny-chat-message"

/**
 * Parse initial messages from server-rendered <shiny-chat-message> elements.
 * These exist as children of <shiny-chat-messages> in the initial HTML.
 */
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
      id: crypto.randomUUID(),
      role,
      content,
      contentType,
      streaming: false,
      icon,
    })
  })

  return messages
}

/**
 * Thin custom element shell for <shiny-chat-container>.
 * Reads attributes from the host element and mounts a React root with <ChatApp />.
 */
class ChatContainerElement extends HTMLElement {
  private reactRoot: Root | null = null

  connectedCallback() {
    if (this.reactRoot) return

    const elementId = this.getAttribute("id") ?? ""
    const iconAssistant = this.getAttribute("icon-assistant") ?? undefined

    // Derive the placeholder from a child <shiny-chat-input> element, if present
    const inputEl = this.querySelector(CHAT_INPUT_TAG)
    const placeholder = inputEl?.getAttribute("placeholder") ?? undefined

    // Derive the inputId: look for a child <shiny-chat-input> with an id,
    // otherwise fall back to "<elementId>_user_input" (the R-side convention)
    const inputId = inputEl?.getAttribute("id") ?? `${elementId}_user_input`

    // Parse initial messages from server-rendered HTML before React takes over
    const initialMessages = parseInitialMessages(this)

    // Unbind any Shiny inputs/outputs in the server-rendered content before
    // React replaces the DOM. Without this, Shiny's internal binding registry
    // retains stale references, preventing re-binding of the new React-rendered
    // elements (Shiny thinks the inputs are already bound by ID).
    transport.unbindAll(this)

    this.reactRoot = createRoot(this)
    this.reactRoot.render(
      createElement(ChatApp, {
        transport,
        elementId,
        iconAssistant,
        inputId,
        placeholder,
        initialMessages,
      }),
    )
  }

  disconnectedCallback() {
    this.reactRoot?.unmount()
    this.reactRoot = null
  }
}

if (!customElements.get("shiny-chat-container")) {
  customElements.define("shiny-chat-container", ChatContainerElement)
}
