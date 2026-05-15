import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { ChatApp } from "./ChatApp"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ChatMessageData } from "./state"
import type { ContentType } from "../transport/types"
import { uuid } from "../utils/uuid"

// Single shared transport instance for all chat instances on the page
const transport = getShinyTransport()

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
      contentType,
      streaming: false,
      icon,
      blocks: [{ type: "content", content, contentType }],
    })
  })

  return messages
}

class ChatContainerElement extends HTMLElement {
  private reactRoot: Root | null = null

  connectedCallback() {
    if (this.reactRoot) return

    const elementId = this.getAttribute("id") ?? ""
    const iconAssistant = this.getAttribute("icon-assistant") ?? undefined
    const enableCancel = this.hasAttribute("enable-cancel")

    const inputEl = this.querySelector(CHAT_INPUT_TAG)
    const placeholder = inputEl?.getAttribute("placeholder") ?? undefined

    // Falls back to "<elementId>_user_input" (the R package's convention)
    const inputId = inputEl?.getAttribute("id") ?? `${elementId}_user_input`
    const cancelId = `${elementId}_cancel`

    const initialMessages = parseInitialMessages(this)

    const footerEl = this.querySelector(CHAT_FOOTER_TAG)
    const footerHtml = footerEl ? footerEl.innerHTML : undefined

    // Unbind any Shiny inputs/outputs in the server-rendered content before
    // React replaces the DOM. Without this, Shiny's internal binding registry
    // retains stale references, preventing re-binding of the new React-rendered
    // elements (Shiny thinks the inputs are already bound by ID).
    transport.unbindAll(this)

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
        enableCancel,
        footerHtml,
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
