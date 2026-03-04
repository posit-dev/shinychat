import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import { ShinyTransport } from "../transport/shiny-transport"

// Import chat-tools.ts to register shiny-tool-request and shiny-tool-result
// custom elements (Lit-based implementation still used for these)
import "./chat-tools"

// Single shared transport instance for all chat instances on the page
const transport = new ShinyTransport()

const CHAT_INPUT_TAG = "shiny-chat-input"

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
    const inputId =
      inputEl?.getAttribute("id") ?? `${elementId}_user_input`

    this.reactRoot = createRoot(this)
    this.reactRoot.render(
      createElement(ChatApp, {
        transport,
        elementId,
        iconAssistant,
        inputId,
        placeholder,
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
