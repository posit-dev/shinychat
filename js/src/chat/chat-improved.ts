import React from "react"
import { createRoot, Root } from "react-dom/client"
import { ChatApp } from "./components-improved"
import type {
  ChatAppRef,
  Message,
  UpdateUserInput,
} from "./components-improved"
import { renderDependencies, showShinyClientMessage } from "../utils/_utils"
import type { HtmlDep } from "../utils/_utils"

// Types for Shiny integration
type ShinyChatMessage = {
  id: string
  handler: string
  obj: (Message & { html_deps?: HtmlDep[] }) | null
}

// The single web component that contains the entire React chat app
class ChatContainer extends HTMLElement {
  private _root: Root | null = null
  private _chatAppRef: React.RefObject<ChatAppRef> = React.createRef()

  static get observedAttributes() {
    return ["icon-assistant"]
  }

  get iconAssistant(): string {
    return this.getAttribute("icon-assistant") || ""
  }

  set iconAssistant(value: string) {
    this.setAttribute("icon-assistant", value)
  }

  connectedCallback() {
    if (!this._root) {
      this._root = createRoot(this)
    }
    this.render()
  }

  disconnectedCallback() {
    if (this._root) {
      this._root.unmount()
      this._root = null
    }
  }

  attributeChangedCallback() {
    this.render()
  }

  private render() {
    if (!this._root) return

    const iconAssistant = this.getAttribute("icon-assistant") || ""
    const id = this.getAttribute("id") || ""

    this._root.render(
      React.createElement(ChatApp, {
        ref: this._chatAppRef,
        iconAssistant,
        id,
      }),
    )
  }

  // Public API for external access
  updateUserInput(update: UpdateUserInput) {
    if (this._chatAppRef.current) {
      this._chatAppRef.current.updateUserInput(update)
    }
  }
}

// Register the web component
if (!customElements.get("shiny-chat-container")) {
  customElements.define("shiny-chat-container", ChatContainer)
}

// Shiny message handler
async function handleShinyChatMessage(message: ShinyChatMessage) {
  if (message.obj?.html_deps) {
    await renderDependencies(message.obj.html_deps)
  }

  const evt = new CustomEvent(message.handler, {
    detail: message.obj,
  })

  const el = document.getElementById(message.id)

  if (!el) {
    showShinyClientMessage({
      status: "error",
      message: `Unable to handle Chat() message since element with id
        ${message.id} wasn't found. Do you need to call .ui() (Express) or need a
        chat_ui('${message.id}') in the UI (Core)?
      `,
    })
    return
  }

  el.dispatchEvent(evt)
}

// Register Shiny message handler
if (typeof window !== "undefined" && window.Shiny) {
  window.Shiny.addCustomMessageHandler(
    "shinyChatMessage",
    handleShinyChatMessage,
  )
}

// Constants for backwards compatibility
const CHAT_CONTAINER_TAG = "shiny-chat-container"

export { ChatContainer, CHAT_CONTAINER_TAG }
