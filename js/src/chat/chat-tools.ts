import { LitElement, html, TemplateResult } from "lit"
import { property } from "lit/decorators.js"
import { unsafeHTML } from "lit/directives/unsafe-html.js"

/**
 * Custom event interface for hiding tool requests
 */
declare global {
  interface Window {
    shinychat: {
      hiddenToolRequests: Set<string>
    }
  }
  interface GlobalEventHandlersEventMap {
    "shiny-tool-request-hide": CustomEvent<{ request_id: string }>
  }
}

// TODO: remove this hack and rely only on events
window.shinychat = window.shinychat || {}
window.shinychat.hiddenToolRequests =
  window.shinychat.hiddenToolRequests || new Set<string>()

window.addEventListener("shiny-tool-request-hide", (event: CustomEvent) => {
  const { request_id: requestId } = event.detail
  if (!requestId) return
  window.shinychat.hiddenToolRequests.add(requestId)
  const toolRequestElement = document.querySelector<HTMLElement>(
    `.shiny-tool-request[request-id="${requestId}"]`,
  )
  if (!toolRequestElement) return
  toolRequestElement.hidden = true
})

/**
 * Base class for a collapsible tool request or result card component.
 *
 * @element shiny-tool-card
 * @extends LitElement
 */
class ShinyToolCard extends LitElement {
  /**
   * Unique identifier for the tool request or result. This value links a
   * request to a result and is therefore not unique on the page.
   * @property {string} requestId
   * @attr request-id
   */
  @property({ type: String, attribute: "request-id" })
  requestId!: string

  /**
   * Name of the tool being executed, e.g. `get_weather`.
   * @property {string} name
   * @attr tool-name
   */
  @property({ type: String, attribute: "tool-name" })
  toolName!: string

  /**
   * Display title for the card. If not provided, falls back to `toolName`.
   * @property {string} title
   * @attr tool-title
   */
  @property({ type: String, attribute: "tool-title" })
  toolTitle?: string

  /**
   * Optional intent description explaining the purpose of the tool execution.
   * This value is shown in the card header with the class "tool-intent".
   * @property {string | undefined} intent
   */
  @property({ type: String })
  intent?: string

  /**
   * Controls whether the card content is expanded/visible.
   * @property {boolean} expanded
   * @attr expanded
   * @default false
   */
  @property({ type: Boolean, reflect: true })
  expanded = false

  /**
   * CSS class(es) to apply for status styling (e.g., "text-danger" for errors).
   * @property {string} classStatus
   */
  @property({ type: String })
  classStatus: string = ""

  /**
   * HTML content for the icon displayed in the card header.
   * @property {string} icon
   */
  @property({ type: String })
  icon: string = ""

  /**
   * Template string for formatting the card title. {title} is replaced with the
   * actual title.
   * @property {string} titleTemplate
   * @default "{title}"
   */
  @property({ type: String })
  titleTemplate: string = "{title}"

  createRenderRoot(): ShinyToolCard {
    return this
  }

  #toggleCollapse(e: Event) {
    e.preventDefault()
    const card = (e.target as HTMLElement).closest(".shiny-tool-card")
    if (card?.hasAttribute("fullscreen")) return
    this.expanded = !this.expanded
    this.requestUpdate()
  }

  firstUpdated() {
    this.dispatchEvent(new CustomEvent("shiny-chat-maybe-scroll-to-bottom"))
  }

  /**
   * Formats the title for display in the card header. Uses the `titleTemplate`,
   * replacing `{title}` with the actual title or name of the tool.
   */
  protected formatTitle() {
    let displayTitle = this.toolTitle || `${this.toolName}()`
    displayTitle = `<span class="tool-title-name">${displayTitle}</span>`
    displayTitle = this.titleTemplate.replace("{title}", displayTitle)
    return html`${unsafeHTML(displayTitle)}`
  }

  /**
   * Renders the card with the provided body content.
   * @param {TemplateResult} bodyContent - The content to display in the card
   *   body.
   */
  protected renderCard(bodyContent: TemplateResult) {
    const headerId = `tool-header-${this.requestId}`
    const contentId = `tool-content-${this.requestId}`
    const icon = this.icon || ICONS.wrenchAdjustable

    const headerContent = html`
      <div class="tool-icon ${this.classStatus}">${unsafeHTML(icon)}</div>
      <div class="tool-title ${this.classStatus}">${this.formatTitle()}</div>
      <div class="tool-spacer"></div>
      ${this.intent ? html`<div class="tool-intent">${this.intent}</div>` : ""}
    `

    return html`
      <div
        class="shiny-tool-card card bslib-card html-fill-item html-fill-container m-0"
      >
        <button
          class="card-header"
          id="${headerId}"
          @click="${this.#toggleCollapse}"
          aria-expanded="${this.expanded}"
          aria-controls="${contentId}"
        >
          ${headerContent}
          <div class="collapse-indicator">${unsafeHTML(ICONS.plus)}</div>
        </button>
        <div
          class="card-body bslib-gap-spacing html-fill-item html-fill-container${this
            .expanded
            ? ""
            : " collapsed"}"
          id="${contentId}"
          role="region"
          aria-labelledby="${headerId}"
          ?inert="${!this.expanded}"
        >
          ${bodyContent}
        </div>
      </div>
    `
  }
}

/**
 * Web component that displays information about a tool request.
 *
 * @element shiny-tool-request
 * @extends ShinyToolCard
 */
export class ShinyToolRequest extends ShinyToolCard {
  /**
   * The function arguments as requested by the LLM, typically in JSON format.
   * @property {string} arguments
   * @attr
   */
  @property({ type: String })
  arguments!: string

  /**
   * Controls the visibility of the tool request component.
   * When true, the component is hidden from view.
   * @property {boolean} hidden
   * @attr
   * @default false
   */
  @property({ type: Boolean, reflect: true })
  hidden = false

  constructor() {
    super()
    this.classList.add("shiny-tool-request")
    this.titleTemplate = "Running {title}"
    this.icon = '<div class="spinner-border" role="status"></div>'
  }

  connectedCallback() {
    super.connectedCallback()
    this.hidden = window.shinychat.hiddenToolRequests.has(this.requestId)
  }

  render() {
    if (this.hidden) {
      return html``
    }

    const bodyContent = html`
      <shiny-markdown-stream
        content="${markdownCodeBlock(this.arguments, "json")}"
        content-type="markdown"
        ?streaming=${false}
      ></shiny-markdown-stream>
    `

    return this.renderCard(
      html`<div class="shiny-tool-request__arguments">
        <strong>Tool arguments</strong> ${bodyContent}
      </div>`,
    )
  }
}

/**
 * Web component that displays the result of a tool execution.
 *
 * @element shiny-tool-result
 * @extends ShinyToolCard
 * @fires shiny-tool-request-hide - Event fired to hide any corresponding tool
 *   requests on the page.
 */
export class ShinyToolResult extends ShinyToolCard {
  /**
   * Controls whether the card has a fullscreen toggle button.
   * @property {boolean} fullScreen
   * @attr full-screen
   * @default false
   */
  @property({ type: Boolean, reflect: true, attribute: "full-screen" })
  fullScreen = false

  #overlay: HTMLDivElement | null = null
  #triggerElement: HTMLElement | null = null

  /**
   * The original tool call that generated this result. Used to display the tool
   * invocation.
   * @property {string | undefined} requestCall
   * @attr request-call
   */
  @property({ type: String, attribute: "request-call" })
  requestCall?: string

  /**
   * The status of the tool execution. When set to "error", displays in an error
   * state with red text and an exclamation icon.
   * @property {string} status
   */
  @property({ type: String })
  status!: string

  /**
   * Should the tool request should be displayed alongside the result?
   * @property {boolean} showRequest
   * @attr show-request
   * @default true
   */
  @property({ type: Boolean, attribute: "show-request" })
  showRequest = false

  /**
   * The actual result content returned by the tool execution.
   * @property {string} value
   */
  @property({ type: String })
  value!: string

  /**
   * Specifies how the value should be rendered. Supported types:
   * - "html": Renders the value as raw HTML
   * - "text": Renders the value as plain text in a paragraph
   * - "markdown": Renders the value as Markdown (default)
   * - "code": Renders the value as a code block
   * Any other value defaults to markdown rendering.
   * @property {string} valueType
   * @attr value-type
   */
  @property({ type: String, attribute: "value-type" })
  valueType!: string

  constructor() {
    super()
    this.classList.add("shiny-tool-result")
    this.titleTemplate = "{title}"
  }

  #enterFullscreen(e: Event) {
    e.preventDefault()
    e.stopPropagation()
    if (this.#overlay) return

    const card = (e.target as HTMLElement).closest(
      ".shiny-tool-card",
    ) as HTMLElement | null
    if (!card) return

    this.#triggerElement = (e.target as HTMLElement).closest(
      ".tool-fullscreen-toggle",
    ) as HTMLElement | null

    this.expanded = true
    this.requestUpdate()

    card.setAttribute("fullscreen", "")
    window.dispatchEvent(new Event("resize"))

    this.#overlay = this.#createOverlay()
    document.body.append(this.#overlay)

    document.addEventListener("keydown", this.#trapFocusExit, true)
    card.setAttribute("tabindex", "-1")
    card.focus()
  }

  #exitFullscreen() {
    const card = this.querySelector(
      ".shiny-tool-card[fullscreen]",
    ) as HTMLElement | null
    if (!card) return

    card.removeAttribute("fullscreen")
    card.removeAttribute("tabindex")
    window.dispatchEvent(new Event("resize"))

    this.#overlay?.remove()
    this.#overlay = null

    document.removeEventListener("keydown", this.#trapFocusExit, true)

    this.#triggerElement?.focus()
    this.#triggerElement = null
  }

  #createOverlay(): HTMLDivElement {
    const overlay = document.createElement("div")
    overlay.className = "shiny-tool-fullscreen-backdrop"
    overlay.onclick = () => this.#exitFullscreen()

    const closeBtn = document.createElement("button")
    closeBtn.type = "button"
    closeBtn.className = "shiny-tool-fullscreen-exit"
    closeBtn.setAttribute("aria-expanded", "true")
    closeBtn.setAttribute("aria-label", "Close card")
    closeBtn.onclick = (ev) => {
      ev.stopPropagation()
      this.#exitFullscreen()
    }
    closeBtn.innerHTML = `Close ${ICONS.xLg}`

    overlay.append(closeBtn)
    return overlay
  }

  #trapFocusExit = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      const target = e.target as HTMLElement
      if (
        target.matches("select[open]") ||
        target.matches("input[aria-expanded='true']")
      ) {
        return
      }
      this.#exitFullscreen()
      e.preventDefault()
      return
    }

    if (e.key !== "Tab") return

    const card = this.querySelector(
      ".shiny-tool-card[fullscreen]",
    ) as HTMLElement | null
    if (!card || !this.#overlay) return

    const cardFocusable = [
      ...card.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ].filter((el) => el.offsetParent !== null)
    const closeBtn = this.#overlay.querySelector<HTMLElement>(
      ".shiny-tool-fullscreen-exit",
    )
    if (!closeBtn) return
    const firstInCard = cardFocusable[0]
    const lastInCard = cardFocusable[cardFocusable.length - 1]
    const active = document.activeElement

    if (!e.shiftKey && (active === lastInCard || active === card)) {
      e.preventDefault()
      closeBtn.focus()
    } else if (!e.shiftKey && active === closeBtn) {
      e.preventDefault()
      ;(firstInCard ?? card).focus()
    } else if (e.shiftKey && (active === firstInCard || active === card)) {
      e.preventDefault()
      closeBtn.focus()
    } else if (e.shiftKey && active === closeBtn) {
      e.preventDefault()
      ;(lastInCard ?? card).focus()
    } else if (!card.contains(active as Node) && active !== closeBtn) {
      e.preventDefault()
      card.focus()
    }
  }

  disconnectedCallback() {
    super.disconnectedCallback()
    this.#exitFullscreen()
  }

  connectedCallback() {
    super.connectedCallback()
    if (this.status === "error") {
      this.classStatus = "text-danger"
      this.icon = ICONS.exclamationCircleFill
      this.titleTemplate = "{title} failed"
    }
    this.dispatchEvent(
      new CustomEvent("shiny-tool-request-hide", {
        detail: { request_id: this.requestId },
        bubbles: true,
        cancelable: true,
      }),
    )
  }

  /**
   * Renders the tool result content.
   */
  #renderResult() {
    let result: string | TemplateResult = ""
    const value = this.value || "[Empty result]"

    if (this.valueType === "html") {
      result = html`${unsafeHTML(value)}`
    } else if (this.valueType === "text") {
      result = html`<p>${value}</p>`
    } else {
      // markdown, code, or default
      if (this.valueType !== "markdown") {
        // If value_type is "code", we format it as a markdown code block
        result = markdownCodeBlock(value, "text")
      }

      result = html`<shiny-markdown-stream
        content=${result || value}
        content-type="markdown"
        ?streaming=${false}
      ></shiny-markdown-stream>`
    }

    if (!this.showRequest && this.valueType === "html") {
      return result
    }

    const resultHeader = this.showRequest
      ? html`<strong>Tool result</strong> `
      : ""

    return html`<div class="shiny-tool-result__result">
      ${resultHeader}${result}
    </div>`
  }

  /**
   * Renders the tool request call, if applicable.
   * If the request call is long, it will be wrapped in a <details> element.
   */
  #renderRequest() {
    if (!this.showRequest || !this.requestCall) {
      return ""
    }

    const request = html`<shiny-markdown-stream
      content="${markdownCodeBlock(this.requestCall, "")}"
      content-type="markdown"
      ?streaming=${false}
    ></shiny-markdown-stream>`

    const isLongRequest = this.requestCall.split("\n").length > 2

    return html`<div class="shiny-tool-result__request">
      ${isLongRequest
        ? html`<details>
            <summary>Tool call</summary>
            ${request}
          </details>`
        : html`<strong>Tool call</strong> ${request}`}
    </div>`
  }

  #renderFullscreenToggle() {
    if (!this.fullScreen) return ""
    const contentId = `tool-content-${this.requestId}`
    return html`
      <button
        class="tool-fullscreen-toggle badge rounded-pill"
        @click="${this.#enterFullscreen}"
        aria-label="Expand card"
        aria-expanded="false"
        aria-controls="${contentId}"
        type="button"
      >
        ${unsafeHTML(ICONS.fullscreenEnter)}
      </button>
    `
  }

  render() {
    const bodyContent = html`
      ${this.#renderRequest()} ${this.#renderResult()}
      ${this.#renderFullscreenToggle()}
    `

    return this.renderCard(bodyContent)
  }
}

const ICONS = {
  exclamationCircleFill: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-exclamation-circle-fill" viewBox="0 0 16 16">
  <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0M8 4a.905.905 0 0 0-.9.995l.35 3.507a.552.552 0 0 0 1.1 0l.35-3.507A.905.905 0 0 0 8 4m.002 6a1 1 0 1 0 0 2 1 1 0 0 0 0-2"/>
</svg>`,
  wrenchAdjustable: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-wrench-adjustable" viewBox="0 0 16 16">
  <path d="M16 4.5a4.5 4.5 0 0 1-1.703 3.526L13 5l2.959-1.11q.04.3.041.61"/>
  <path d="M11.5 9c.653 0 1.273-.139 1.833-.39L12 5.5 11 3l3.826-1.53A4.5 4.5 0 0 0 7.29 6.092l-6.116 5.096a2.583 2.583 0 1 0 3.638 3.638L9.908 8.71A4.5 4.5 0 0 0 11.5 9m-1.292-4.361-.596.893.809-.27a.25.25 0 0 1 .287.377l-.596.893.809-.27.158.475-1.5.5a.25.25 0 0 1-.287-.376l.596-.893-.809.27a.25.25 0 0 1-.287-.377l.596-.893-.809.27-.158-.475 1.5-.5a.25.25 0 0 1 .287.376M3 14a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/>
</svg>`,
  plus: `<svg xmlns="http://www.w3.org/2000/svg" width="10px" height="10px" viewBox="4 4 12 12" fill="none">
  <path class="horizontal" d="M5 11C4.44772 11 4 10.5523 4 10C4 9.44772 4.44772 9 5 9H15C15.5523 9 16 9.44772 16 10C16 10.5523 15.5523 11 15 11H5Z" fill="currentColor"/>
  <path class="vertical" d="M9 5C9 4.44772 9.44772 4 10 4C10.5523 4 11 4.44772 11 5V15C11 15.5523 10.5523 16 10 16C9.44772 16 9 15.5523 9 15V5Z" fill="currentColor"/>
</svg>`,
  fullscreenEnter: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" style="height:1em;width:1em;fill:currentColor;" aria-hidden="true" role="img"><path d="M20 5C20 4.4 19.6 4 19 4H13C12.4 4 12 3.6 12 3C12 2.4 12.4 2 13 2H21C21.6 2 22 2.4 22 3V11C22 11.6 21.6 12 21 12C20.4 12 20 11.6 20 11V5ZM4 19C4 19.6 4.4 20 5 20H11C11.6 20 12 20.4 12 21C12 21.6 11.6 22 11 22H3C2.4 22 2 21.6 2 21V13C2 12.4 2.4 12 3 12C3.6 12 4 12.4 4 13V19Z"/></svg>`,
  xLg: `<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" fill="currentColor" class="bi bi-x-lg" viewBox="0 0 16 16"><path d="M2.146 2.854a.5.5 0 1 1 .708-.708L8 7.293l5.146-5.147a.5.5 0 0 1 .708.708L8.707 8l5.147 5.146a.5.5 0 0 1-.708.708L8 8.707l-5.146 5.147a.5.5 0 0 1-.708-.708L7.293 8z"/></svg>`,
}

/**
 * Formats a string as a Markdown code block with the specified language.
 * Defaults to "markdown" if no language is provided.
 *
 * @param {string} content - The content to include in the code block.
 * @param {string} [language="markdown"] - The programming language for syntax
 *   highlighting.
 * @returns {string} - The formatted Markdown code block.
 */
const markdownCodeBlock = (content: string, language: string = "markdown") => {
  const backticks = "`".repeat(8)
  return `${backticks}${language}\n${content}\n${backticks}`
}

window.Shiny?.addCustomMessageHandler(
  "shiny-tool-request-hide",
  (request_id) => {
    const event = new CustomEvent("shiny-tool-request-hide", {
      detail: { request_id },
      bubbles: true,
      cancelable: true,
    })
    window.dispatchEvent(event)
  },
)

declare global {
  interface HTMLElementTagNameMap {
    "shiny-tool-request": ShinyToolRequest
    "shiny-tool-result": ShinyToolResult
  }
}
