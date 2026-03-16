import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import { MarkdownStream, type MarkdownStreamApi } from "./MarkdownStream"
import { ShinyLifecycleContext } from "../chat/context"
import { getShinyTransport } from "../transport/shiny-transport"
import type { ContentType } from "../transport/types"
import type { HtmlDep } from "rstudio-shiny/srcts/types/src/shiny/render"

// Single shared transport instance for standalone markdown-stream usage
const transport = getShinyTransport()

type ContentMessage = {
  id: string
  content: string
  operation: "append" | "replace"
  html_deps?: HtmlDep[]
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

class MarkdownStreamElement extends HTMLElement {
  private reactRoot: Root | null = null
  private api: MarkdownStreamApi | null = null
  private pendingMessages: (ContentMessage | IsStreamingMessage)[] = []

  connectedCallback() {
    if (this.reactRoot) return

    this.reactRoot = createRoot(this)

    const initialContent = this.getAttribute("content") ?? ""
    const initialContentType =
      (this.getAttribute("content-type") as ContentType) ?? "markdown"
    const initialStreaming = readBooleanAttr(this, "streaming")
    const autoScroll = readBooleanAttr(this, "auto-scroll")

    this.reactRoot.render(
      createElement(
        ShinyLifecycleContext.Provider,
        { value: transport },
        createElement(MarkdownStream, {
          initialContent,
          initialContentType,
          initialStreaming,
          autoScroll,
          onApiReady: (api: MarkdownStreamApi) => {
            this.api = api
            for (const msg of this.pendingMessages) {
              this.dispatchMessage(msg)
            }
            this.pendingMessages = []
          },
        }),
      ),
    )
  }

  disconnectedCallback() {
    this.reactRoot?.unmount()
    this.reactRoot = null
    this.api = null
    this.pendingMessages = []
  }

  handleMessage(message: ContentMessage | IsStreamingMessage) {
    if (!this.api) {
      this.pendingMessages.push(message)
      return
    }
    this.dispatchMessage(message)
  }

  private dispatchMessage(message: ContentMessage | IsStreamingMessage) {
    if (isStreamingMessage(message)) {
      this.api!.setStreaming(message.isStreaming)
      return
    }

    if (message.operation === "replace") {
      this.api!.replaceContent(message.content)
    } else if (message.operation === "append") {
      this.api!.appendContent(message.content)
    }
  }
}

function attributeToPropertyName(name: string): string {
  return name.replace(/-([a-z])/g, (_, letter: string) => letter.toUpperCase())
}

function readBooleanAttr(el: HTMLElement, name: string): boolean {
  const attrValue = el.getAttribute(name)

  if (attrValue === "" || attrValue === "true") return true
  if (attrValue === "false") return false

  const propertyName = attributeToPropertyName(name)
  const propertyValue = (el as unknown as Record<string, unknown>)[propertyName]

  return propertyValue === true || propertyValue === "true"
}

if (!customElements.get("shiny-markdown-stream")) {
  customElements.define("shiny-markdown-stream", MarkdownStreamElement)
}

window.Shiny?.addCustomMessageHandler(
  "shinyMarkdownStreamMessage",
  async (message: ContentMessage | IsStreamingMessage) => {
    const el = document.getElementById(
      message.id,
    ) as MarkdownStreamElement | null

    if (!el) {
      transport.showClientMessage({
        status: "error",
        message: `Unable to handle MarkdownStream() message since element with id ${message.id} wasn't found.`,
      })
      return
    }

    if (!isStreamingMessage(message) && message.html_deps) {
      await transport.renderDependencies(message.html_deps)
    }

    el.handleMessage(message)
  },
)
