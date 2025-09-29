import React from "react"
import { createRoot, Root } from "react-dom/client"
import { MarkdownStream } from "../chat/components"
import { renderDependencies, showShinyClientMessage } from "../utils/_utils"
import type { HtmlDep } from "../utils/_utils"

type ContentType = "markdown" | "semi-markdown" | "html" | "text"

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

// Type guard
function isStreamingMessage(
  message: ContentMessage | IsStreamingMessage,
): message is IsStreamingMessage {
  return "isStreaming" in message
}

// Simple web component that mounts a React MarkdownStream
class MarkdownElement extends HTMLElement {
  private _root: Root | null = null
  private _content = ""
  private _contentType: ContentType = "markdown"
  private _streaming = false
  private _autoScroll = false
  private _onContentChange?: () => void
  private _onStreamEnd?: () => void

  static get observedAttributes() {
    return ["content", "content-type", "streaming", "auto-scroll"]
  }

  get content() {
    return this._content
  }
  set content(value: string) {
    this._content = value
    this.render()
  }

  get content_type() {
    return this._contentType
  }
  set content_type(value: ContentType) {
    this._contentType = value
    this.render()
  }

  get streaming() {
    return this._streaming
  }
  set streaming(value: boolean) {
    this._streaming = value
    this.render()
  }

  get auto_scroll() {
    return this._autoScroll
  }
  set auto_scroll(value: boolean) {
    this._autoScroll = value
    this.render()
  }

  get onContentChange() {
    return this._onContentChange
  }
  set onContentChange(value: (() => void) | undefined) {
    this._onContentChange = value
    this.render()
  }

  get onStreamEnd() {
    return this._onStreamEnd
  }
  set onStreamEnd(value: (() => void) | undefined) {
    this._onStreamEnd = value
    this.render()
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

  attributeChangedCallback(
    name: string,
    oldValue: string | null,
    newValue: string | null,
  ) {
    switch (name) {
      case "content":
        this.content = newValue || ""
        break
      case "content-type":
        this.content_type = (newValue as ContentType) || "markdown"
        break
      case "streaming":
        this.streaming = newValue !== null
        break
      case "auto-scroll":
        this.auto_scroll = newValue !== null
        break
    }
  }

  private render() {
    if (!this._root) return

    this._root.render(
      React.createElement(MarkdownStream, {
        content: this._content,
        contentType: this._contentType,
        streaming: this._streaming,
        autoScroll: this._autoScroll,
        onContentChange: this._onContentChange,
        onStreamEnd: this._onStreamEnd,
      }),
    )
  }
}

// Register custom element
if (!customElements.get("shiny-markdown-stream")) {
  customElements.define("shiny-markdown-stream", MarkdownElement)
}

// Message handler for markdown stream
async function handleMessage(
  message: ContentMessage | IsStreamingMessage,
): Promise<void> {
  const el = document.getElementById(message.id) as MarkdownElement

  if (!el) {
    showShinyClientMessage({
      status: "error",
      message: `Unable to handle MarkdownStream() message since element with id
      ${message.id} wasn't found. Do you need to call .ui() (Express) or need a
      output_markdown_stream('${message.id}') in the UI (Core)?`,
    })
    return
  }

  if (isStreamingMessage(message)) {
    el.streaming = message.isStreaming
    return
  }

  if (message.html_deps) {
    await renderDependencies(message.html_deps)
  }

  if (message.operation === "replace") {
    el.setAttribute("content", message.content)
  } else if (message.operation === "append") {
    const content = el.getAttribute("content") || ""
    el.setAttribute("content", content + message.content)
  } else {
    throw new Error(`Unknown operation: ${message.operation}`)
  }
}

// Register Shiny message handler
if (typeof window !== "undefined" && window.Shiny) {
  window.Shiny.addCustomMessageHandler(
    "shinyMarkdownStreamMessage",
    handleMessage,
  )
}

export { MarkdownElement }
