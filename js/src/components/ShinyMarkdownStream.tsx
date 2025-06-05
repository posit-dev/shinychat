import { StrictMode } from "preact/compat"
import { render } from "preact/compat"
import { MarkdownStream, ContentType } from "./MarkdownStream"
import { renderDependencies, showShinyClientMessage } from "../utils/_utils"
import type { HtmlDep } from "../utils/_utils"

export type ContentMessage = {
  id: string
  content: string
  operation: "append" | "replace"
  html_deps?: HtmlDep[]
}

export type IsStreamingMessage = {
  id: string
  isStreaming: boolean
}

// Type guard
function isStreamingMessage(
  message: ContentMessage | IsStreamingMessage,
): message is IsStreamingMessage {
  return "isStreaming" in message
}

export class ShinyMarkdownStreamOutput extends HTMLElement {
  private rootElement?: HTMLElement
  private content: string = ""
  private contentType: ContentType = "markdown"
  private streaming: boolean = false
  private autoScroll: boolean = false

  connectedCallback() {
    // Don't use shadow DOM so the component can inherit styles from the main document
    const root = document.createElement("div")
    root.classList.add("html-fill-container", "html-fill-item")
    this.appendChild(root)

    this.rootElement = root

    // Read initial attributes
    this.content = this.getAttribute("content") || ""
    this.contentType =
      (this.getAttribute("content-type") as ContentType) || "markdown"
    this.streaming = this.hasAttribute("streaming")
    this.autoScroll = this.hasAttribute("auto-scroll")

    // Initial render
    this.renderValue()
  }

  disconnectedCallback() {
    if (this.rootElement) {
      render(null, this.rootElement)
    }
  }

  private renderValue() {
    if (!this.rootElement) return

    render(
      <StrictMode>
        <MarkdownStream
          content={this.content}
          contentType={this.contentType}
          streaming={this.streaming}
          autoScroll={this.autoScroll}
          onContentChange={this.handleContentChange}
          onStreamEnd={this.handleStreamEnd}
        />
      </StrictMode>,
      this.rootElement,
    )
  }

  // Public callback methods for React component and testing
  handleContentChange = () => {
    // Callback for when content changes - can be used for custom logic
    this.dispatchEvent(
      new CustomEvent("contentchange", {
        detail: { content: this.content },
      }),
    )
  }

  handleStreamEnd = () => {
    // Callback for when streaming ends - can be used for custom logic
    this.dispatchEvent(new CustomEvent("streamend"))
  }

  // Public methods for updating from Shiny messages
  updateContent(content: string, operation: "append" | "replace" = "replace") {
    if (operation === "replace") {
      this.content = content
    } else if (operation === "append") {
      this.content += content
    }
    this.setAttribute("content", this.content)
    this.renderValue()
  }

  setStreaming(streaming: boolean) {
    this.streaming = streaming
    if (streaming) {
      this.setAttribute("streaming", "")
    } else {
      this.removeAttribute("streaming")
    }
    this.renderValue()
  }

  setContentType(contentType: ContentType) {
    this.contentType = contentType
    this.setAttribute("content-type", contentType)
    this.renderValue()
  }

  setAutoScroll(autoScroll: boolean) {
    this.autoScroll = autoScroll
    if (autoScroll) {
      this.setAttribute("auto-scroll", "")
    } else {
      this.removeAttribute("auto-scroll")
    }
    this.renderValue()
  }
}

// Register the custom element
if (!customElements.get("shiny-markdown-stream")) {
  customElements.define("shiny-markdown-stream", ShinyMarkdownStreamOutput)
}

// Shiny message handler
async function handleShinyMarkdownStreamMessage(
  message: ContentMessage | IsStreamingMessage,
): Promise<void> {
  const el = document.getElementById(message.id) as ShinyMarkdownStreamOutput

  if (!el) {
    showShinyClientMessage({
      status: "error",
      message: `Unable to handle MarkdownStream() message since element with id ${message.id} wasn't found. Do you need to call .ui() (Express) or need a output_markdown_stream('${message.id}') in the UI (Core)?`,
    })
    return
  }

  if (isStreamingMessage(message)) {
    el.setStreaming(message.isStreaming)
    return
  }

  // Render HTML dependencies first
  if (message.html_deps) {
    await renderDependencies(message.html_deps)
  }

  // Update content
  el.updateContent(message.content, message.operation)
}

// Register the Shiny message handler
if (window.Shiny) {
  window.Shiny.addCustomMessageHandler(
    "shinyMarkdownStreamMessage",
    handleShinyMarkdownStreamMessage,
  )
}

export { handleShinyMarkdownStreamMessage }
