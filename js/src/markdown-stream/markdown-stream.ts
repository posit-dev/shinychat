import { PropertyValues, html, nothing } from "lit"
import { repeat } from "lit/directives/repeat.js"
import { unsafeHTML } from "lit-html/directives/unsafe-html.js"
import { property } from "lit/decorators.js"

import ClipboardJS from "clipboard"
import hljs from "highlight.js/lib/common"
import { Renderer, parse } from "marked"

import { CHAT_CONTAINER_TAG } from "../chat/chat"

import {
  LightElement,
  createElement,
  createSVGIcon,
  renderDependencies,
  sanitizeHTML,
  showShinyClientMessage,
  throttle,
} from "../utils/_utils"

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

// SVG dot to indicate content is currently streaming
const SVG_DOT_CLASS = "markdown-stream-dot"
const SVG_DOT = createSVGIcon(
  `<svg width="12" height="12" xmlns="http://www.w3.org/2000/svg" class="${SVG_DOT_CLASS}" style="margin-left:.25em;margin-top:-.25em"><circle cx="6" cy="6" r="6"/></svg>`,
)

// 'markdown' renderer (for assistant messages)
const markdownRenderer = new Renderer()

// Add some basic Bootstrap styling to markdown tables
markdownRenderer.table = (header: string, body: string) => {
  return `<table class="table table-striped table-bordered">
      <thead>${header}</thead>
      <tbody>${body}</tbody>
    </table>`
}

const defaultMarkdownCodeRenderer = markdownRenderer.code

markdownRenderer.code = function (
  code: string,
  infostring: string | undefined,
  escaped: boolean,
): string {
  if (infostring === "{=html}") {
    return code
  }
  return defaultMarkdownCodeRenderer.call(this, code, infostring, escaped)
}

// 'semi-markdown' renderer (for user messages)
const semiMarkdownRenderer = new Renderer()

// Escape HTML, not for security reasons, but just because it's confusing if the user is
// using tag-like syntax to demarcate parts of their prompt for other reasons (like
// <User>/<Assistant> for providing examples to the model), and those tags vanish.
semiMarkdownRenderer.html = (html: string) =>
  html
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;")

function contentToHTML(content: string, content_type: ContentType) {
  if (content_type === "markdown") {
    const html = parse(content, { renderer: markdownRenderer })
    return unsafeHTML(sanitizeHTML(html as string))
  } else if (content_type === "semi-markdown") {
    const html = parse(content, { renderer: semiMarkdownRenderer })
    return unsafeHTML(sanitizeHTML(html as string))
  } else if (content_type === "html") {
    return unsafeHTML(sanitizeHTML(content))
  } else if (content_type === "text") {
    return content
  } else {
    throw new Error(`Unknown content type: ${content_type}`)
  }
}

class MarkdownElement extends LightElement {
  @property() content = ""
  @property({ attribute: "content-type" })
  content_type: ContentType = "markdown"
  @property({ type: Boolean, reflect: true })
  streaming = false
  @property({ type: Boolean, reflect: true, attribute: "auto-scroll" })
  auto_scroll = false
  @property({ type: Function }) onContentChange?: () => void
  @property({ type: Function }) onStreamEnd?: () => void

  // ------- Incremental rendering -------
  // Avoids O(n²) markdown parsing during streaming by splitting content into
  // "committed" blocks (parsed once, cached) and a "pending" tail (re-parsed).
  // At stream end, we re-parse the full content to fix any split artifacts.

  #committedBlocks: Array<{ id: number; html: string }> = []
  #pendingMarkdown = ""
  #pendingHtml = ""
  #fenceCount = 0 // odd = inside code fence
  #lastProcessedIndex = 0
  #blockIdCounter = 0
  #pendingUpdateScheduled = false
  #lastPendingUpdate = 0

  #countFences(text: string): number {
    return (text.match(/^`{3,}/gm) || []).length
  }

  #parseMarkdown(markdown: string): string {
    if (!markdown.trim()) return ""
    if (this.content_type === "markdown") {
      return sanitizeHTML(
        parse(markdown, { renderer: markdownRenderer }) as string,
      )
    } else if (this.content_type === "semi-markdown") {
      return sanitizeHTML(
        parse(markdown, { renderer: semiMarkdownRenderer }) as string,
      )
    }
    return ""
  }

  #processContent(): void {
    const newContent = this.content.slice(this.#lastProcessedIndex)
    if (!newContent) return

    this.#fenceCount += this.#countFences(newContent)
    this.#pendingMarkdown += newContent
    this.#lastProcessedIndex = this.content.length

    // Commit at \n\n boundaries when outside code fences
    if (this.#fenceCount % 2 === 0) {
      const boundary = this.#pendingMarkdown.lastIndexOf("\n\n")
      if (boundary !== -1) {
        const toCommit = this.#pendingMarkdown.slice(0, boundary)
        if (toCommit.trim()) {
          this.#committedBlocks.push({
            id: this.#blockIdCounter++,
            html: this.#parseMarkdown(toCommit),
          })
        }
        this.#pendingMarkdown = this.#pendingMarkdown.slice(boundary + 2)
      }
    }

    this.#schedulePendingUpdate()
  }

  #schedulePendingUpdate(): void {
    const len = this.#pendingMarkdown.length

    // Skip parsing for very large pending buffers (e.g., huge tables)
    if (len > 5000) {
      this.#pendingHtml = ""
      return
    }

    // Throttle based on content length: larger buffers update less frequently.
    // Naturally handles tables (large) vs prose (small) without special-casing.
    const throttleMs = Math.min(50 + Math.floor(len / 4), 400)
    const now = performance.now()

    if (now - this.#lastPendingUpdate >= throttleMs) {
      this.#pendingHtml = this.#parseMarkdown(this.#pendingMarkdown)
      this.#lastPendingUpdate = now
    } else if (!this.#pendingUpdateScheduled) {
      this.#pendingUpdateScheduled = true
      window.setTimeout(
        () => {
          this.#pendingUpdateScheduled = false
          this.#pendingHtml = this.#parseMarkdown(this.#pendingMarkdown)
          this.#lastPendingUpdate = performance.now()
          this.requestUpdate()
        },
        throttleMs - (now - this.#lastPendingUpdate),
      )
    }
  }

  #finalizeStream(): void {
    // Re-parse full content to fix any artifacts from block splitting
    const fullHtml = this.#parseMarkdown(this.content)
    this.#committedBlocks = [{ id: 0, html: fullHtml }]
    this.#pendingMarkdown = ""
    this.#pendingHtml = ""
  }

  #resetIncrementalState(): void {
    this.#committedBlocks = []
    this.#pendingMarkdown = ""
    this.#pendingHtml = ""
    this.#fenceCount = 0
    this.#lastProcessedIndex = 0
    this.#pendingUpdateScheduled = false
    this.#lastPendingUpdate = 0
  }

  render() {
    if (
      (this.content_type === "markdown" ||
        this.content_type === "semi-markdown") &&
      (this.#committedBlocks.length > 0 || this.#pendingHtml)
    ) {
      return html`
        ${repeat(
          this.#committedBlocks,
          (block) => block.id,
          (block) => unsafeHTML(block.html),
        )}${this.#pendingHtml ? unsafeHTML(this.#pendingHtml) : nothing}
      `
    }
    return html`${contentToHTML(this.content, this.content_type)}`
  }

  connectedCallback(): void {
    super.connectedCallback()
    this.addEventListener(
      "shiny-chat-maybe-scroll-to-bottom",
      this.#onMaybeScrollToBottom,
    )
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.#cleanup()
  }

  protected willUpdate(changedProperties: PropertyValues): void {
    if (changedProperties.has("content")) {
      this.#isContentBeingAdded = true

      // Reset incremental state on content replacement (vs append)
      const oldContent = changedProperties.get("content") as string | undefined
      if (
        oldContent !== undefined &&
        (this.content.length < oldContent.length ||
          !this.content.startsWith(oldContent))
      ) {
        this.#resetIncrementalState()
      }

      if (
        this.content_type === "markdown" ||
        this.content_type === "semi-markdown"
      ) {
        this.#processContent()
      }

      MarkdownElement.#doUnBind(this)
    }
    super.willUpdate(changedProperties)
  }

  protected updated(changedProperties: Map<string, unknown>): void {
    if (changedProperties.has("content")) {
      // Post-process DOM after content has been added
      try {
        this.#highlightAndCodeCopy()
      } catch (error) {
        console.warn("Failed to highlight code:", error)
      }

      // Render Shiny HTML dependencies and bind inputs/outputs
      if (this.streaming) {
        this.#appendStreamingDot()
        MarkdownElement._throttledBind(this)
      } else {
        MarkdownElement.#doBind(this)
      }

      // Update scrollable element after content has been added
      this.#updateScrollableElement()

      // Possibly scroll to bottom after content has been added
      this.#isContentBeingAdded = false
      this.#maybeScrollToBottom()

      if (this.onContentChange) {
        try {
          this.onContentChange()
        } catch (error) {
          console.warn("Failed to call onContentUpdate callback:", error)
        }
      }
    }

    if (changedProperties.has("streaming")) {
      if (this.streaming) {
        this.#appendStreamingDot()
      } else {
        this.#finalizeStream()
        this.#removeStreamingDot()
        if (this.onStreamEnd) {
          try {
            this.onStreamEnd()
          } catch (error) {
            console.warn("Failed to call onStreamEnd callback:", error)
          }
        }
      }
    }
  }

  #appendStreamingDot(): void {
    this.#removeStreamingDot()

    if (this.content.trim() === "") {
      return
    }
    if (this.lastElementChild?.tagName.toLowerCase() === "shiny-tool-request") {
      return
    }

    const hasText = (node: Text): boolean => /\S/.test(node.textContent || "")

    // We go into these elements to find the innermost streaming element
    const recurseInto = new Set(["p", "div", "pre", "ul", "ol"])
    // We can put the dot in these kinds of containers
    const inlineContainers = new Set([
      "p",
      "h1",
      "h2",
      "h3",
      "h4",
      "h5",
      "h6",
      "li",
      "code",
    ])

    /**
     * Find the innermost element where streaming is happening, i.e. where the
     * streaming is appending new content.
     */
    const findInnermostStreamingElement = (element: Element): Element => {
      let current = element
      let depth = 0

      while (depth < 5) {
        depth++
        const children = current.childNodes

        let lastMeaningfulChild: Node | null = null

        // Find last meaningful child
        for (let i = children.length - 1; i >= 0; i--) {
          const child = children[i]
          if (!child) break
          if (
            child.nodeType === Node.ELEMENT_NODE ||
            (child.nodeType === Node.TEXT_NODE && hasText(child as Text))
          ) {
            lastMeaningfulChild = child
            break
          }
        }

        if (!lastMeaningfulChild || !(lastMeaningfulChild instanceof Element)) {
          // If no meaningful child, or last child is a text node, streaming
          // is happening the `current` element.
          return current
        }

        const tagName = lastMeaningfulChild.tagName.toLowerCase()

        if (recurseInto.has(tagName)) {
          current = lastMeaningfulChild
          continue // Keep drilling down to find innermost streaming element
        }

        return inlineContainers.has(tagName) ? lastMeaningfulChild : current
      }

      return current
    }

    findInnermostStreamingElement(this).appendChild(SVG_DOT)
  }

  #removeStreamingDot(): void {
    this.querySelector(`svg.${SVG_DOT_CLASS}`)?.remove()
  }

  static async #doUnBind(el: HTMLElement): Promise<void> {
    if (!window?.Shiny?.unbindAll) return

    try {
      window.Shiny.unbindAll(el)
    } catch (err) {
      showShinyClientMessage({
        status: "error",
        message: `Failed to unbind Shiny inputs/outputs: ${err}`,
      })
    }
  }

  static async #doBind(el: HTMLElement): Promise<void> {
    if (!window?.Shiny?.initializeInputs) return
    if (!window?.Shiny?.bindAll) return

    try {
      window.Shiny.initializeInputs(el)
    } catch (err) {
      showShinyClientMessage({
        status: "error",
        message: `Failed to initialize Shiny inputs: ${err}`,
      })
    }

    try {
      await window.Shiny.bindAll(el)
    } catch (err) {
      showShinyClientMessage({
        status: "error",
        message: `Failed to bind Shiny inputs/outputs: ${err}`,
      })
    }
  }

  @throttle(200)
  private static async _throttledBind(el: HTMLElement): Promise<void> {
    await this.#doBind(el)
  }

  #highlightAndCodeCopy(): void {
    const el = this.querySelector("pre code")
    if (!el) return
    this.querySelectorAll<HTMLElement>("pre code").forEach((el) => {
      if (el.dataset.highlighted === "yes") return

      hljs.highlightElement(el)

      // Add copy button
      const btn = createElement("button", {
        class: "code-copy-button",
        title: "Copy to clipboard",
      })
      btn.innerHTML = '<i class="bi"></i>'
      el.prepend(btn)

      // Setup clipboard
      const clipboard = new ClipboardJS(btn, { target: () => el })
      clipboard.on("success", (e) => {
        btn.classList.add("code-copy-button-checked")
        setTimeout(() => btn.classList.remove("code-copy-button-checked"), 2000)
        e.clearSelection()
      })
    })
  }

  // ------- Scrolling logic -------

  // Nearest scrollable parent element (if any)
  #scrollableElement: HTMLElement | null = null
  // Whether content is currently being added to the element
  #isContentBeingAdded = false
  // Whether the user has scrolled away from the bottom
  #isUserScrolled = false

  #onScroll = (): void => {
    if (!this.#isContentBeingAdded) {
      this.#isUserScrolled = !this.#isNearBottom()
    }
  }

  #isNearBottom(): boolean {
    const el = this.#scrollableElement
    if (!el) return false

    return el.scrollHeight - (el.scrollTop + el.clientHeight) < 50
  }

  #updateScrollableElement(): void {
    const el = this.#findScrollableParent()

    if (el !== this.#scrollableElement) {
      this.#scrollableElement?.removeEventListener("scroll", this.#onScroll)
      this.#scrollableElement = el
      this.#scrollableElement?.addEventListener("scroll", this.#onScroll)
    }
  }

  #findScrollableParent(): HTMLElement | null {
    if (!this.auto_scroll) return null

    // eslint-disable-next-line
    let el: HTMLElement | null = this
    while (el) {
      if (el.scrollHeight > el.clientHeight) return el
      el = el.parentElement
      if (el?.tagName?.toLowerCase() === CHAT_CONTAINER_TAG.toLowerCase()) {
        // This ensures that we do not accidentally scroll a parent element of the chat
        // container. If the chat container itself is scrollable, a scrollable element
        // would already have been identified.
        break
      }
    }
    return null
  }

  #onMaybeScrollToBottom = (): void => {
    this.#maybeScrollToBottom()
  }

  #maybeScrollToBottom(): void {
    const el = this.#scrollableElement
    if (!el || this.#isUserScrolled) return

    el.scroll({
      top: el.scrollHeight - el.clientHeight,
      behavior: this.streaming ? "instant" : "smooth",
    })
  }

  #cleanup(): void {
    this.#scrollableElement?.removeEventListener("scroll", this.#onScroll)
    this.#scrollableElement = null
    this.#isUserScrolled = false
    this.removeEventListener(
      "shiny-chat-maybe-scroll-to-bottom",
      this.#onMaybeScrollToBottom,
    )
    this.#resetIncrementalState()
  }
}

// ------- Register custom elements and shiny bindings ---------

if (!customElements.get("shiny-markdown-stream")) {
  customElements.define("shiny-markdown-stream", MarkdownElement)
}

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
    const content = el.getAttribute("content")
    el.setAttribute("content", content + message.content)
  } else {
    throw new Error(`Unknown operation: ${message.operation}`)
  }
}

window.Shiny?.addCustomMessageHandler(
  "shinyMarkdownStreamMessage",
  handleMessage,
)

export { MarkdownElement, contentToHTML }
