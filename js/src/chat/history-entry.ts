import { createElement, useSyncExternalStore } from "react"
import { createRoot, type Root } from "react-dom/client"
import { ChatHistoryContent } from "./ChatHistoryDrawer"
import { getHistoryStore } from "./historyStore"

function ExternalHistory({ elementId }: { elementId: string }) {
  const store = getHistoryStore(elementId)
  const history = useSyncExternalStore(
    store.subscribe,
    store.getSnapshot,
    store.getSnapshot,
  )

  if (!history.initialized || !history.enabled) return null

  return createElement(
    "div",
    {
      className: "shiny-chat-history shiny-chat-history-inline",
      role: "region",
      "aria-label": "Conversation history",
    },
    createElement(ChatHistoryContent, {
      conversations: history.conversations,
      activeId: history.activeId,
      busy: history.busy,
      connected: history.connected,
      onSelect: store.actions.select,
      onNew: store.actions.create,
      onRename: store.actions.rename,
      onDelete: store.actions.delete,
    }),
  )
}

class ChatHistoryElement extends HTMLElement {
  private reactRoot: Root | null = null
  private pendingUnmount: ReturnType<typeof setTimeout> | null = null

  static observedAttributes = ["for"]

  connectedCallback() {
    // A DOM move disconnects and reconnects the element in the same task. Keep
    // the existing root so its search/menu/edit state and store subscription
    // remain intact.
    if (this.pendingUnmount !== null) {
      clearTimeout(this.pendingUnmount)
      this.pendingUnmount = null
    }

    this.renderHistory()
  }

  attributeChangedCallback() {
    if (this.isConnected) this.renderHistory()
  }

  disconnectedCallback() {
    // Match the chat container's deferred teardown so moving an inline history
    // view cannot produce duplicate roots or stale subscriptions.
    this.pendingUnmount = setTimeout(() => {
      this.reactRoot?.unmount()
      this.reactRoot = null
      this.pendingUnmount = null
    }, 0)
  }

  private renderHistory() {
    const elementId = this.getAttribute("for")?.trim()
    if (!elementId) {
      this.dataset.historyError = "missing-for"
      this.reactRoot?.unmount()
      this.reactRoot = null
      return
    }

    delete this.dataset.historyError
    if (!this.reactRoot) {
      this.reactRoot = createRoot(this)
    }
    this.reactRoot.render(
      createElement(ExternalHistory, { elementId, key: elementId }),
    )
  }
}

if (!customElements.get("shiny-chat-history")) {
  customElements.define("shiny-chat-history", ChatHistoryElement)
}
