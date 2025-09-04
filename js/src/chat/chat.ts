import { LitElement, html } from "lit"
import { unsafeHTML } from "lit-html/directives/unsafe-html.js"
import { property } from "lit/decorators.js"

import {
  LightElement,
  createElement,
  renderDependencies,
  showShinyClientMessage,
  generateRandomId,
} from "../utils/_utils"

import { ShinyToolRequest, ShinyToolResult } from "./chat-tools"

import { MarkdownElement as ShinyMarkdownStream } from "../markdown-stream/markdown-stream"

import type { HtmlDep } from "../utils/_utils"
import { icons as ICONS } from "../utils/_icons"

type ContentType = "markdown" | "html" | "text" | "semi-markdown"

type ChatMessagePayload = {
  role: string
  content: string
  contentType: ContentType
  icon?: string
  html_deps?: HtmlDep[]
}

type ChatMessageStartPayload = {
  streamId?: string
  role: string
  contentType: ContentType
  icon?: string
}

type ChatMessageAppendPayload = {
  streamId?: string
  operation: "append" | "replace"
  content: string
  icon?: string
  role?: string
  contentType?: ContentType
  html_deps?: HtmlDep[]
}

type ChatMessageEndPayload = {
  streamId?: string
}

type ShinyChatMessage = {
  id: string
  handler: string
  obj:
    | ChatMessagePayload
    | ChatMessageStartPayload
    | ChatMessageAppendPayload
    | ChatMessageEndPayload
}

type UpdateUserInput = {
  value?: string
  placeholder?: string
  submit?: false
  focus?: false
}

// https://github.com/microsoft/TypeScript/issues/28357#issuecomment-748550734
declare global {
  interface GlobalEventHandlersEventMap {
    "shiny-chat-input-sent": CustomEvent<ChatMessagePayload>
    "shiny-chat-input-enable": CustomEvent
    "shiny-chat-message": CustomEvent<ChatMessagePayload>
    "shiny-chat-message-start": CustomEvent<ChatMessageStartPayload>
    "shiny-chat-message-append": CustomEvent<ChatMessageAppendPayload>
    "shiny-chat-message-end": CustomEvent<ChatMessageEndPayload>
    "shiny-chat-clear-messages": CustomEvent
    "shiny-chat-update-user-input": CustomEvent<UpdateUserInput>
    "shiny-chat-remove-loading-message": CustomEvent
  }
}

const CHAT_MESSAGE_TAG = "shiny-chat-message"
const CHAT_MESSAGE_USER_TAG = "shiny-user-message"
const CHAT_MESSAGE_LOADING_TAG = "shiny-chat-message-loading"
const CHAT_MESSAGES_TAG = "shiny-chat-messages"
const CHAT_INPUT_TAG = "shiny-chat-input"
const CHAT_CONTAINER_TAG = "shiny-chat-container"
const CHAT_TOOL_REQUEST_TAG = "shiny-tool-request"
const CHAT_TOOL_RESULT_TAG = "shiny-tool-result"

class ChatMessage extends HTMLElement {
  // ChatMessage is *not* a LitElement because we want to manage rendering
  // manually to avoid re-renders when updating content streams. This component
  // is a simple container for icon and content areas, plus a method to create
  // new content streams as needed.
  private _icon = ""
  private _role: string = "assistant"
  private _content: string = ""
  private _contentType: ContentType = "markdown"
  private _initialized = false

  constructor() {
    super()

    // Initialize properties from attributes
    this._content = this.getAttribute("content") || ""
    this._contentType =
      (this.getAttribute("content-type") as ContentType) || "markdown"

    const role = this.getAttribute("data-role")
    if (role) this._role = role

    this.#initializeElement()
  }

  connectedCallback() {
    // Only render initial content on first connection, not on reconnects
    if (!this._initialized) {
      this._initialized = true
      this.#renderInitialContent()
    }
  }

  get icon() {
    return this._icon
  }
  set icon(value: string | undefined) {
    this._icon = value ? value : ""
    if (value) {
      this.setAttribute("icon", "")
    } else {
      this.removeAttribute("icon")
    }
    this.#updateIcon()
  }

  get role() {
    return this._role
  }
  set role(value: string) {
    this._role = value
    this.setAttribute("data-role", value)
    this.#updateIcon()
  }

  get content() {
    return this._content
  }
  set content(value: string) {
    this._content = value
    this.#renderInitialContent()
  }

  get contentType() {
    return this._contentType
  }
  set contentType(value: ContentType) {
    this._contentType = value
    this.setAttribute("content-type", value)
  }

  // Attribute observation for external attribute changes
  static get observedAttributes() {
    return ["data-role", "content-type"]
  }

  attributeChangedCallback(name: string, oldValue: string, newValue: string) {
    if (oldValue === newValue) return

    switch (name) {
      case "data-role":
        this._role = newValue as "user" | "assistant" | "loading"
        this.#updateIcon()
        break
      case "content-type":
        this._contentType = newValue as ContentType
        break
    }
  }

  #initializeElement() {
    const icon = this.#messageIcon()
    this.innerHTML = `
      ${icon}
      <div class="message-content"></div>
    `
  }

  #updateIcon() {
    const iconContainer = this.querySelector(".message-icon")
    const newIcon = this.#getIcon()

    if (newIcon && iconContainer) {
      iconContainer.innerHTML = newIcon
    } else if (newIcon && !iconContainer) {
      const iconDiv = document.createElement("div")
      iconDiv.className = "message-icon"
      iconDiv.innerHTML = newIcon
      this.prepend(iconDiv)
    } else if (!newIcon && iconContainer) {
      iconContainer.remove()
    }
  }

  #messageIcon() {
    const icon = this.#getIcon()
    return icon ? `<div class="message-icon">${icon}</div>` : ""
  }

  #getIcon() {
    if (this.role != "user") {
      return this.icon || ICONS.robot
    }

    return this.icon
  }

  async #renderInitialContent() {
    if (!this.content) return
    const existingInitStream = this.contentContainer.querySelector(
      "[data-stream-id='__init__']",
    )
    if (existingInitStream) {
      existingInitStream.remove()
    }

    const stream = await this.createStream("__init__", this.contentType, false)
    stream.content = this.content
    stream.streaming = false

    // Make sure the initial stream is the first stream
    this.contentContainer.prepend(stream)
  }

  get contentContainer(): HTMLElement {
    return this.querySelector(".message-content") as HTMLElement
  }

  async createStream(
    streamId: string,
    contentType: ContentType,
    streaming = false,
  ): Promise<ShinyMarkdownStream> {
    const stream = createElement("shiny-markdown-stream", {
      "data-stream-id": streamId,
      content: "",
      "content-type": contentType,
      streaming: streaming ? "" : null,
      "auto-scroll": this.role === "assistant" ? "" : null,
    }) as ShinyMarkdownStream

    // Set up content change and stream end handlers
    stream.onContentChange = this.#makeSuggestionsAccessible.bind(this)
    stream.onStreamEnd = this.#makeSuggestionsAccessible.bind(this)

    this.contentContainer.appendChild(stream)

    return stream
  }

  #makeSuggestionsAccessible(): void {
    this.querySelectorAll(".suggestion,[data-suggestion]").forEach((el) => {
      if (!(el instanceof HTMLElement)) return
      if (el.hasAttribute("tabindex")) return

      el.setAttribute("tabindex", "0")
      el.setAttribute("role", "button")

      const suggestion = el.dataset.suggestion || el.textContent
      el.setAttribute("aria-label", `Use chat suggestion: ${suggestion}`)
    })
  }
}

class ChatMessageUser extends ChatMessage {
  constructor() {
    super()
    this.role = "user"
  }
}

class ChatMessageLoading extends ChatMessage {
  constructor() {
    super()
    this.role = "loading"
    this.icon = ICONS.dotsFade
  }
}

class ChatMessages extends LightElement {
  render() {
    return html``
  }
}

interface ChatInputSetInputOptions {
  submit?: boolean
  focus?: boolean
}

class ChatInput extends LightElement {
  @property() placeholder = "Enter a message..."
  // disabled is reflected manually because `reflect: true` doesn't work with LightElement
  @property({ type: Boolean })
  get disabled() {
    return this._disabled
  }

  set disabled(value: boolean) {
    const oldValue = this._disabled
    if (value === oldValue) {
      return
    }

    this._disabled = value
    if (value) {
      this.setAttribute("disabled", "")
    } else {
      this.removeAttribute("disabled")
    }

    this.requestUpdate("disabled", oldValue)
    this.#onInput()
  }

  private _disabled = false
  private _isComposing = false
  inputVisibleObserver?: IntersectionObserver

  connectedCallback(): void {
    super.connectedCallback()

    this.inputVisibleObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) this.#updateHeight()
      })
    })

    this.inputVisibleObserver.observe(this)
    this.addEventListener("compositionstart", this.#onCompositionStart)
    this.addEventListener("compositionend", this.#onCompositionEnd)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()
    this.inputVisibleObserver?.disconnect()
    this.inputVisibleObserver = undefined
    this.removeEventListener("compositionstart", this.#onCompositionStart)
    this.removeEventListener("compositionend", this.#onCompositionEnd)
  }

  attributeChangedCallback(
    name: string,
    _old: string | null,
    value: string | null,
  ) {
    super.attributeChangedCallback(name, _old, value)
    if (name === "disabled") {
      this.disabled = value !== null
    }
  }

  private get textarea(): HTMLTextAreaElement {
    return this.querySelector("textarea") as HTMLTextAreaElement
  }

  private get value(): string {
    return this.textarea.value
  }

  private get valueIsEmpty(): boolean {
    return this.value.trim().length === 0
  }

  private get button(): HTMLButtonElement {
    return this.querySelector("button") as HTMLButtonElement
  }

  render() {
    const icon = ICONS.arrowUpCircleFill

    return html`
      <textarea
        id="${this.id}"
        class="form-control"
        rows="1"
        placeholder="${this.placeholder}"
        @keydown=${this.#onKeyDown}
        @input=${this.#onInput}
        data-shiny-no-bind-input
      ></textarea>
      <button
        type="button"
        title="Send message"
        aria-label="Send message"
        @click=${this.#sendInput}
      >
        ${unsafeHTML(icon)}
      </button>
    `
  }

  // Pressing enter sends the message (if not empty)
  #onKeyDown(e: KeyboardEvent): void {
    const isEnter = e.code === "Enter" && !e.shiftKey
    if (isEnter && !this._isComposing && !this.valueIsEmpty) {
      e.preventDefault()
      this.#sendInput()
    }
  }

  #onInput(): void {
    this.#updateHeight()
    this.button.disabled = this.disabled ? true : this.value.trim().length === 0
  }

  #onCompositionStart(): void {
    this._isComposing = true
  }

  #onCompositionEnd(): void {
    this._isComposing = false
  }

  // Determine whether the button should be enabled/disabled on first render
  protected firstUpdated(): void {
    this.#onInput()
  }

  #sendInput(focus = true): void {
    if (this.valueIsEmpty) return
    if (this.disabled) return

    window.Shiny.setInputValue!(this.id, this.value, { priority: "event" })

    // Emit event so parent element knows to insert the message
    const sentEvent = new CustomEvent("shiny-chat-input-sent", {
      detail: { content: this.value, role: "user" },
      bubbles: true,
      composed: true,
    })
    this.dispatchEvent(sentEvent)

    this.setInputValue("")
    this.disabled = true

    if (focus) this.textarea.focus()
  }

  #updateHeight(): void {
    const el = this.textarea
    if (el.scrollHeight == 0) {
      return
    }
    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }

  setInputValue(
    value: string,
    { submit = false, focus = false }: ChatInputSetInputOptions = {},
  ): void {
    // Store previous value to restore post-submit (if submitting)
    const oldValue = this.textarea.value

    this.textarea.value = value

    // Simulate an input event (to trigger the textarea autoresize)
    const inputEvent = new Event("input", { bubbles: true, cancelable: true })
    this.textarea.dispatchEvent(inputEvent)

    if (submit) {
      this.#sendInput(false)
      if (oldValue) this.setInputValue(oldValue)
    }

    if (focus) {
      this.textarea.focus()
    }
  }
}

class ChatContainer extends LightElement {
  @property({ attribute: "icon-assistant" }) iconAssistant = ""
  inputSentinelObserver?: IntersectionObserver
  private loadingIndicator: HTMLElement | null = null
  private activeStreams = new Map<string, Promise<ShinyMarkdownStream>>()

  private get input(): ChatInput {
    return this.querySelector(CHAT_INPUT_TAG) as ChatInput
  }

  private get messages(): ChatMessages {
    return this.querySelector(CHAT_MESSAGES_TAG) as ChatMessages
  }

  private get lastMessage(): ChatMessage | null {
    const last = this.messages.lastElementChild
    return last ? (last as ChatMessage) : null
  }

  render() {
    return html``
  }

  connectedCallback(): void {
    super.connectedCallback()

    // We use a sentinel element that we place just above the shiny-chat-input. When it
    // moves off-screen we know that the text area input is now floating, add shadow.
    let sentinel = this.querySelector<HTMLElement>("div")
    if (!sentinel) {
      sentinel = createElement("div", {
        style: "width: 100%; height: 0;",
      }) as HTMLElement
      this.input.insertAdjacentElement("afterend", sentinel)
    }

    this.inputSentinelObserver = new IntersectionObserver(
      (entries) => {
        const inputTextarea = this.input.querySelector("textarea")
        if (!inputTextarea) return
        const addShadow = entries[0]?.intersectionRatio === 0
        inputTextarea.classList.toggle("shadow", addShadow)
      },
      {
        threshold: [0, 1],
        rootMargin: "0px",
      },
    )

    this.inputSentinelObserver.observe(sentinel)
  }

  firstUpdated(): void {
    // Don't attach event listeners until child elements are rendered
    if (!this.messages) return

    this.addEventListener("shiny-chat-input-sent", this.#onInputSent)
    this.addEventListener("shiny-chat-input-enable", this.#onEnableInput)

    this.addEventListener("shiny-chat-message", this.#onMessage)
    this.addEventListener("shiny-chat-message-start", this.#onMessageStart)
    this.addEventListener("shiny-chat-message-append", this.#onMessageAppend)
    this.addEventListener("shiny-chat-message-end", this.#onMessageEnd)

    this.addEventListener("shiny-chat-clear-messages", this.#onClear)
    this.addEventListener(
      "shiny-chat-update-user-input",
      this.#onUpdateUserInput,
    )
    this.addEventListener(
      "shiny-chat-remove-loading-message",
      this.#onRemoveLoadingMessage,
    )
    this.addEventListener("click", this.#onInputSuggestionClick)
    this.addEventListener("keydown", this.#onInputSuggestionKeydown)
  }

  disconnectedCallback(): void {
    super.disconnectedCallback()

    this.inputSentinelObserver?.disconnect()
    this.inputSentinelObserver = undefined

    this.removeEventListener("shiny-chat-input-sent", this.#onInputSent)
    this.removeEventListener("shiny-chat-input-enable", this.#onEnableInput)

    this.removeEventListener("shiny-chat-message", this.#onMessage)
    this.removeEventListener("shiny-chat-message-start", this.#onMessageStart)
    this.removeEventListener("shiny-chat-message-append", this.#onMessageAppend)
    this.removeEventListener("shiny-chat-message-end", this.#onMessageEnd)

    this.removeEventListener("shiny-chat-clear-messages", this.#onClear)
    this.removeEventListener(
      "shiny-chat-update-user-input",
      this.#onUpdateUserInput,
    )
    this.removeEventListener(
      "shiny-chat-remove-loading-message",
      this.#onRemoveLoadingMessage,
    )
    this.removeEventListener("click", this.#onInputSuggestionClick)
    this.removeEventListener("keydown", this.#onInputSuggestionKeydown)
  }

  /**
   * Find the most recent stream element when streamId is not provided
   */
  #findMostRecentStream(): ShinyMarkdownStream | null {
    const lastMessage = this.lastMessage
    if (!lastMessage) {
      return null
    }

    return lastMessage.contentContainer.querySelector(
      "shiny-markdown-stream:last-child",
    ) as ShinyMarkdownStream | null
  }

  async #onMessage(event: CustomEvent<ChatMessagePayload>): Promise<void> {
    const { role, content, contentType, icon } = event.detail

    this.#removeLoadingIndicator()

    const messageElement = this.#ensureMessageElement(role, icon)
    const streamId = `msg-${Date.now()}`
    const stream = await messageElement.createStream(
      streamId,
      contentType,
      false,
    )

    const streamElement = stream as ShinyMarkdownStream
    streamElement.content = content
    streamElement.streaming = false
  }

  async #onMessageStart(
    event: CustomEvent<ChatMessageStartPayload>,
  ): Promise<void> {
    const { role, contentType, icon } = event.detail
    const streamId = event.detail.streamId || generateRandomId("stream")

    this.#removeLoadingIndicator()

    const messageElement = this.#ensureMessageElement(role, icon)
    const streamPromise = messageElement.createStream(
      streamId,
      contentType,
      true,
    )

    // Store active stream promises so subsequent messages can await them
    this.activeStreams.set(streamId, streamPromise)

    await streamPromise
  }

  async #onMessageAppend(
    event: CustomEvent<ChatMessageAppendPayload>,
  ): Promise<void> {
    const { operation, content } = event.detail
    let stream: ShinyMarkdownStream | null = null

    if (event.detail.streamId) {
      // Use explicit streamId if provided
      stream = (await this.activeStreams.get(event.detail.streamId)) || null
      if (!stream) {
        throw new Error(
          `Stream element with id ${event.detail.streamId} not found`,
        )
      }
    } else {
      // Fallback to most recent stream
      stream = this.#findMostRecentStream()
      if (!stream) {
        const startEvent = this.#toChatMessageStartEvent(event.detail)
        if (!startEvent) {
          throw new Error(
            `No active stream found and unable to create new stream without role and contentType`,
          )
        }
        await this.#onMessageStart(startEvent)
        stream = this.#findMostRecentStream()
        if (!stream) {
          throw new Error(`Failed to create new stream`)
        }
      }
    }

    const streamElement = stream as ShinyMarkdownStream
    if (operation === "append") {
      streamElement.content = streamElement.content + content
    } else {
      streamElement.content = content
    }
  }

  #toChatMessageStartEvent(
    event: ChatMessageAppendPayload,
  ): CustomEvent<ChatMessageStartPayload> | undefined {
    const { streamId, role, contentType, icon } = event
    if (!role) return
    if (!contentType) return

    return new CustomEvent<ChatMessageStartPayload>(
      "shiny-chat-message-start",
      {
        detail: {
          streamId,
          role,
          contentType,
          icon,
        },
        bubbles: true,
      },
    )
  }

  async #onMessageEnd(
    event: CustomEvent<ChatMessageEndPayload>,
  ): Promise<void> {
    let stream: HTMLElement | null = null

    if (event.detail.streamId) {
      // Use explicit streamId if provided
      stream = (await this.activeStreams.get(event.detail.streamId)) || null
      if (stream) {
        this.activeStreams.delete(event.detail.streamId)
      }
    } else {
      // Fallback to most recent stream
      stream = this.#findMostRecentStream()
      if (stream) {
        // Find and remove the corresponding entry from activeStreams
        const streamId = stream.getAttribute("data-stream-id")
        if (streamId && this.activeStreams.has(streamId)) {
          this.activeStreams.delete(streamId)
        }
      }
    }

    if (stream) {
      const streamElement = stream as ShinyMarkdownStream
      streamElement.streaming = false
    }
  }

  #onEnableInput(): void {
    this.input.disabled = false
    this.#removeLoadingIndicator()
  }

  #ensureMessageElement(role: string, icon?: string): ChatMessage {
    const hasLoadingIndicator = this.loadingIndicator !== null
    const lastMessage = this.lastMessage
    const canReuseLastMessage =
      lastMessage && lastMessage.role === role && !hasLoadingIndicator

    if (canReuseLastMessage) {
      return lastMessage
    }

    const el = new ChatMessage()
    el.role = role
    el.icon = icon
    this.messages.appendChild(el)
    return el
  }

  #addLoadingIndicator(): void {
    if (this.loadingIndicator) return

    this.loadingIndicator = new ChatMessageLoading()
    this.messages.appendChild(this.loadingIndicator)
  }

  #removeLoadingIndicator(): void {
    if (this.loadingIndicator) {
      this.loadingIndicator.remove()
      this.loadingIndicator = null
    }
  }

  #onInputSent(event: CustomEvent<ChatMessagePayload>): void {
    const messageEvent = new CustomEvent("shiny-chat-message", {
      detail: {
        role: event.detail.role,
        content: event.detail.content,
        contentType: "semi-markdown" as ContentType,
        icon: event.detail.icon,
      },
      bubbles: true,
    })
    this.dispatchEvent(messageEvent)

    this.#addLoadingIndicator()
  }

  #onClear(): void {
    this.messages.innerHTML = ""
    this.loadingIndicator = null
    this.activeStreams.clear()
  }

  #onUpdateUserInput(event: CustomEvent<UpdateUserInput>): void {
    const { value, placeholder, submit, focus } = event.detail
    if (value !== undefined) {
      this.input.setInputValue(value, { submit, focus })
    }
    if (placeholder !== undefined) {
      this.input.placeholder = placeholder
    }
  }

  #onInputSuggestionClick(e: MouseEvent): void {
    this.#onInputSuggestionEvent(e)
  }

  #onInputSuggestionKeydown(e: KeyboardEvent): void {
    const isEnterOrSpace = e.key === "Enter" || e.key === " "
    if (!isEnterOrSpace) return

    this.#onInputSuggestionEvent(e)
  }

  #onInputSuggestionEvent(e: MouseEvent | KeyboardEvent): void {
    const { suggestion, submit } = this.#getSuggestion(e.target)
    if (!suggestion) return

    e.preventDefault()
    // Cmd/Ctrl + (event) = force submitting
    // Alt/Opt  + (event) = force setting without submitting
    const shouldSubmit =
      e.metaKey || e.ctrlKey ? true : e.altKey ? false : submit

    this.input.setInputValue(suggestion, {
      submit: shouldSubmit,
      focus: !shouldSubmit,
    })
  }

  #getSuggestion(x: EventTarget | null): {
    suggestion?: string
    submit?: boolean
  } {
    if (!(x instanceof HTMLElement)) return {}

    const el = x.closest(".suggestion, [data-suggestion]")
    if (!(el instanceof HTMLElement)) return {}

    const isSuggestion =
      el.classList.contains("suggestion") || el.dataset.suggestion !== undefined
    if (!isSuggestion) return {}

    const suggestion = el.dataset.suggestion || el.textContent

    return {
      suggestion: suggestion || undefined,
      submit:
        el.classList.contains("submit") ||
        el.dataset.suggestionSubmit === "" ||
        el.dataset.suggestionSubmit === "true",
    }
  }

  #onRemoveLoadingMessage(): void {
    this.#removeLoadingIndicator()
  }
}

// ------- Register custom elements and shiny bindings ---------

const chatCustomElements = [
  { tag: CHAT_MESSAGE_TAG, component: ChatMessage },
  { tag: CHAT_MESSAGE_USER_TAG, component: ChatMessageUser },
  { tag: CHAT_MESSAGE_LOADING_TAG, component: ChatMessageLoading },
  { tag: CHAT_MESSAGES_TAG, component: ChatMessages },
  { tag: CHAT_INPUT_TAG, component: ChatInput },
  { tag: CHAT_CONTAINER_TAG, component: ChatContainer },
  { tag: CHAT_TOOL_REQUEST_TAG, component: ShinyToolRequest },
  { tag: CHAT_TOOL_RESULT_TAG, component: ShinyToolResult },
]

chatCustomElements.forEach(({ tag, component }) => {
  if (!customElements.get(tag)) {
    customElements.define(tag, component)
  }
})

window.Shiny?.addCustomMessageHandler(
  "shinyChatMessage",
  async function (message: ShinyChatMessage) {
    if (message.obj && "html_deps" in message.obj && message.obj.html_deps) {
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
  },
)

export { CHAT_CONTAINER_TAG }
