import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { MarkdownStream, type MarkdownStreamApi } from "./MarkdownStream"
import { TransportContext } from "../chat/context"
import { ShinyTransport } from "../transport/shiny-transport"
import type { ContentType } from "../transport/types"

// Single shared transport instance for standalone markdown-stream usage
const transport = new ShinyTransport()

type ContentMessage = {
  id: string
  content: string
  operation: "append" | "replace"
  html_deps?: unknown[]
}

type IsStreamingMessage = {
  id: string
  isStreaming: boolean
}

function isStreamingMessage(
  message: ContentMessage | IsStreamingMessage,
): message is IsStreamingMessage {
  return "isStreaming" in message
}

/**
 * Thin custom element shell for <shiny-markdown-stream>.
 * Mounts a React root and forwards Shiny messages to the React component.
 */
class MarkdownStreamElement extends HTMLElement {
  private reactRoot: Root | null = null
  private api: MarkdownStreamApi | null = null

  connectedCallback() {
    if (this.reactRoot) return

    this.reactRoot = createRoot(this)

    const initialContent = this.getAttribute("content") ?? ""
    const initialContentType = (this.getAttribute("content-type") as ContentType) ?? "markdown"
    const initialStreaming = this.hasAttribute("streaming")
    const autoScroll = this.hasAttribute("auto-scroll")

    const self = this

    this.reactRoot.render(
      createElement(
        TransportContext.Provider,
        { value: transport },
        createElement(MarkdownStream, {
          initialContent,
          initialContentType,
          initialStreaming,
          autoScroll,
          onApiReady: (api: MarkdownStreamApi) => {
            self.api = api
          },
        }),
      ),
    )
  }

  disconnectedCallback() {
    this.reactRoot?.unmount()
    this.reactRoot = null
    this.api = null
  }

  handleMessage(message: ContentMessage | IsStreamingMessage) {
    if (!this.api) return

    if (isStreamingMessage(message)) {
      this.api.setStreaming(message.isStreaming)
      return
    }

    if (message.operation === "replace") {
      this.api.replaceContent(message.content)
    } else if (message.operation === "append") {
      this.api.appendContent(message.content)
    }
  }
}

if (!customElements.get("shiny-markdown-stream")) {
  customElements.define("shiny-markdown-stream", MarkdownStreamElement)
}

// Register Shiny message handler
window.Shiny?.addCustomMessageHandler(
  "shinyMarkdownStreamMessage",
  async (message: ContentMessage | IsStreamingMessage) => {
    const el = document.getElementById(message.id) as MarkdownStreamElement | null

    if (!el) {
      transport.showClientMessage({
        status: "error",
        message: `Unable to handle MarkdownStream() message since element with id ${message.id} wasn't found.`,
      })
      return
    }

    if (!isStreamingMessage(message) && message.html_deps) {
      await transport.renderDependencies(message.html_deps as never[])
    }

    el.handleMessage(message)
  },
)
