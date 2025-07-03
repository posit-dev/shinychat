import { StrictMode } from "preact/compat"
import { render } from "preact/compat"
import { ChatContainer } from "./ChatContainer"
import { renderDependencies, showShinyClientMessage } from "../../utils/_utils"
import type { HtmlDep } from "../../utils/_utils"
import type { Message, UpdateUserInput } from "./types"
import { ShinyClass as Shiny } from "rstudio-shiny/srcts/types/src/shiny"

// Shiny message types
export type ShinyChatMessage = {
  id: string
  handler: string
  // Message keys will create custom element attributes, but html_deps are handled separately
  obj: (Message & { html_deps?: HtmlDep[] }) | null
}

export type ShinyChatUpdateUserInput = {
  id: string
  handler: string
  obj: UpdateUserInput & { html_deps?: HtmlDep[] }
}

export type ShinyChatSimpleMessage = {
  id: string
  handler: string
  obj?: null
}

// Union type for all possible Shiny chat messages
export type AnyShinyChatMessage =
  | ShinyChatMessage
  | ShinyChatUpdateUserInput
  | ShinyChatSimpleMessage

export class ShinyChatOutput extends HTMLElement {
  private rootElement?: HTMLElement
  private iconAssistant: string = ""
  private placeholder: string = "Enter a message..."
  private initialMessages: Message[] = []

  private chatContainerElement(): HTMLElement | null {
    return (
      this.rootElement?.querySelector<HTMLElement>(".chat-container") || null
    )
  }

  private dispatchElement(): HTMLElement {
    const chatContainer = this.chatContainerElement()
    if (chatContainer) {
      return chatContainer
    }

    return this
  }

  #dispatchEvent(event: CustomEvent): void {
    console.log(`📤 Dispatching event: ${event.type}`, {
      element: this.dispatchElement(),
      event,
    })
    this.dispatchElement().dispatchEvent(event)
  }

  connectedCallback() {
    console.log(`🔌 ShinyChatOutput connected: ${this.id}`)

    // Don't use shadow DOM so the component can inherit styles from the main document
    const root = document.createElement("div")
    root.classList.add("html-fill-container", "html-fill-item")
    this.appendChild(root)

    this.rootElement = root

    // Read initial attributes
    this.iconAssistant = this.getAttribute("icon-assistant") || ""
    this.placeholder = this.getAttribute("placeholder") || "Enter a message..."

    // Initial state data will be encoded as a `<script>` child of custom element
    const dataEl = this.querySelector<HTMLScriptElement>(
      "script[data-for-shiny-chat]",
    )
    if (dataEl) {
      try {
        const data = JSON.parse(dataEl.innerText)
        // Handle initial data if provided
        console.log("Initial chat data:", data)
        if (data.messages && Array.isArray(data.messages)) {
          this.initialMessages = data.messages
        }
      } catch (err) {
        console.warn("Failed to parse initial chat data:", err)
      }
    }

    // Initial render
    this.renderValue()
  }

  disconnectedCallback() {
    console.log(`🔌 ShinyChatOutput disconnected: ${this.id}`)
    if (this.rootElement) {
      render(null, this.rootElement)
    }
  }

  private renderValue() {
    if (!this.rootElement) return
    console.log(`🎨 ShinyChatOutput renderValue: ${this.id}`)

    render(
      <StrictMode>
        <ChatContainer
          id={this.id}
          iconAssistant={this.iconAssistant}
          placeholder={this.placeholder}
          onSendMessage={this.handleSendMessage}
          messages={this.initialMessages}
        />
      </StrictMode>,
      this.rootElement,
    )
  }

  // Handle user input sent - send to Shiny server
  private handleSendMessage = (message: Message) => {
    const shiny = window?.Shiny as Shiny
    if (!shiny?.setInputValue) return

    // Send user message to Shiny server
    shiny.setInputValue(`${this.id}_user_input`, message.content, {
      priority: "event",
    })

    // Dispatch event for any local listeners
    this.dispatchEvent(
      new CustomEvent("shiny-chat-input-sent", {
        detail: message,
        bubbles: true,
        composed: true,
      }),
    )
  }

  // Public methods called by Shiny server - these dispatch CustomEvents
  // The React ChatContainer listens for these events and calls hook methods

  appendMessage(message: Message) {
    const event = new CustomEvent("shiny-chat-append-message", {
      detail: message,
    })
    this.#dispatchEvent(event)
  }

  appendMessageChunk(message: Message) {
    const event = new CustomEvent("shiny-chat-append-message-chunk", {
      detail: message,
    })
    this.#dispatchEvent(event)
  }

  clearMessages() {
    const event = new CustomEvent("shiny-chat-clear-messages")
    this.#dispatchEvent(event)
  }

  updateUserInput(update: UpdateUserInput) {
    const event = new CustomEvent("shiny-chat-update-user-input", {
      detail: update,
    })
    this.#dispatchEvent(event)
  }

  removeLoadingMessage() {
    const event = new CustomEvent("shiny-chat-remove-loading-message")
    this.#dispatchEvent(event)
  }

  // Public methods for updating attributes from Shiny
  setIconAssistant(icon: string) {
    this.iconAssistant = icon
    this.setAttribute("icon-assistant", icon)
    this.renderValue()
  }

  setPlaceholder(placeholder: string) {
    this.placeholder = placeholder
    this.setAttribute("placeholder", placeholder)
    this.renderValue()
  }
}

// Register the custom element
if (!customElements.get("shiny-chat-container")) {
  customElements.define("shiny-chat-container", ShinyChatOutput)
}

// Shiny message handler
async function handleShinyChatMessage(
  message: AnyShinyChatMessage,
): Promise<void> {
  console.log(`📥 handleShinyChatMessage:`, message)
  const el = document.getElementById(message.id) as ShinyChatOutput

  if (!el) {
    showShinyClientMessage({
      status: "error",
      message: `Unable to handle Chat() message since element with id ${message.id} wasn't found. Do you need to call .ui() (Express) or need a chat_ui('${message.id}') in the UI (Core)?`,
    })
    return
  }

  // Render HTML dependencies first if they exist
  if (message.obj && "html_deps" in message.obj && message.obj.html_deps) {
    await renderDependencies(message.obj.html_deps)
  }

  // Call the appropriate method based on the handler
  switch (message.handler) {
    case "shiny-chat-append-message":
      if (message.obj) {
        el.appendMessage(message.obj as Message)
      }
      break

    case "shiny-chat-append-message-chunk":
      if (message.obj) {
        el.appendMessageChunk(message.obj as Message)
      }
      break

    case "shiny-chat-clear-messages":
      el.clearMessages()
      break

    case "shiny-chat-update-user-input":
      if (message.obj) {
        el.updateUserInput(message.obj as UpdateUserInput)
      }
      break

    case "shiny-chat-remove-loading-message":
      el.removeLoadingMessage()
      break

    default:
      console.warn(`Unknown chat handler: ${message.handler}`)
  }
}

// Register the Shiny message handler
if (window.Shiny) {
  window.Shiny.addCustomMessageHandler(
    "shinyChatMessage",
    handleShinyChatMessage,
  )
}

export { handleShinyChatMessage }
