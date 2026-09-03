import { createRoot, type Root } from "react-dom/client"
import { createElement } from "react"
import {
  MarkdownStream,
  type ContentSegment,
  type MarkdownStreamApi,
} from "./MarkdownStream"
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
  trusted: boolean
  segment_start: boolean
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
  private pendingUnmount: ReturnType<typeof setTimeout> | null = null

  connectedCallback() {
    // Moving the element in the DOM fires disconnectedCallback then
    // connectedCallback synchronously in the same tick. The deferred teardown
    // scheduled on disconnect hasn't run yet, so cancel it here to keep the
    // live React root (and any streamed content) intact across the move.
    if (this.pendingUnmount !== null) {
      clearTimeout(this.pendingUnmount)
      this.pendingUnmount = null
    }

    if (this.reactRoot) return

    this.reactRoot = createRoot(this)

    const initialContent = this.getAttribute("content") ?? ""
    const initialSegments = readInitialSegments(this, initialContent)
    const initialContentType =
      (this.getAttribute("content-type") as ContentType) ?? "markdown"
    const initialStreaming = readBooleanAttr(this, "streaming")
    const initialTrusted = readBooleanAttr(this, "content-trusted")
    const autoScroll = readBooleanAttr(this, "auto-scroll")

    this.reactRoot.render(
      createElement(
        ShinyLifecycleContext.Provider,
        { value: transport },
        createElement(MarkdownStream, {
          initialContent,
          initialSegments,
          initialContentType,
          initialStreaming,
          initialTrusted,
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
    // Defer teardown so a move (disconnect immediately followed by reconnect)
    // can cancel it. If the element is genuinely removed, no reconnect cancels
    // the timer and cleanup runs on the next tick.
    this.pendingUnmount = setTimeout(() => {
      this.reactRoot?.unmount()
      this.reactRoot = null
      this.api = null
      this.pendingMessages = []
      this.pendingUnmount = null
    }, 0)
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
      this.api!.replaceContent(message.content, message.trusted === true)
    } else if (message.operation === "append") {
      this.api!.appendContent(
        message.content,
        message.trusted === true,
        message.segment_start === true,
      )
    }
  }
}

function readInitialSegments(
  el: HTMLElement,
  fallbackContent: string,
): ContentSegment[] | undefined {
  const encoded = el.getAttribute("content-segments")
  if (encoded === null) return undefined

  try {
    const value: unknown = JSON.parse(encoded)
    if (
      Array.isArray(value) &&
      value.every(
        (segment) =>
          typeof segment === "object" &&
          segment !== null &&
          typeof (segment as Record<string, unknown>).text === "string" &&
          typeof (segment as Record<string, unknown>).trusted === "boolean",
      )
    ) {
      return value as ContentSegment[]
    }
  } catch {
    // Malformed provenance must fail closed.
  }
  return [{ text: fallbackContent, trusted: false }]
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
