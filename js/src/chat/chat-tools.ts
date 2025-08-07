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
    this.expanded = !this.expanded
    this.requestUpdate()
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

    const headerContent = html`
      <div class="tool-icon ${this.classStatus}">${unsafeHTML(this.icon)}</div>
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
    this.titleTemplate = "Running {title}"
    this.icon = '<div class="spinner-border" role="status"></div>'
  }

  connectedCallback() {
    super.connectedCallback()
    this.hidden = window.shinychat.hiddenToolRequests.has(this.requestId)
    window.addEventListener("shiny-tool-request-hide", this.#onToolRequestHide)
  }

  disconnectedCallback() {
    super.disconnectedCallback()
    window.removeEventListener(
      "shiny-tool-request-hide",
      this.#onToolRequestHide,
    )
  }

  #onToolRequestHide = (event: CustomEvent) => {
    if (event.detail.request_id === this.requestId) {
      this.hidden = true
    }
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
    this.titleTemplate = "{title}"
  }

  connectedCallback() {
    super.connectedCallback()
    // Set status class and icon based on status
    if (this.status === "error") {
      this.classStatus = "text-danger"
      this.icon = ICONS.exclamationCircleFill
      this.titleTemplate = "{title} failed"
    } else if (!this.icon) {
      this.icon = ICONS.wrenchAdjustable
    }
    // Emit event to hide the corresponding tool request
    window.shinychat.hiddenToolRequests.add(this.requestId)
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

    if (this.valueType === "html") {
      result = html`${unsafeHTML(this.value)}`
    } else if (this.valueType === "text") {
      result = html`<p>${this.value}</p>`
    } else {
      // markdown, code, or default
      if (this.valueType !== "markdown") {
        // If value_type is "code", we format it as a markdown code block
        result = markdownCodeBlock(this.value, "text")
      }

      result = html`<shiny-markdown-stream
        content=${result || this.value}
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

  render() {
    const bodyContent = html` ${this.#renderRequest()} ${this.#renderResult()} `

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
    window.shinychat.hiddenToolRequests.add(request_id)
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
