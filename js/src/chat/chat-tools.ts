import { LitElement, html, TemplateResult } from "lit"
import { property } from "lit/decorators.js"
import { unsafeHTML } from "lit/directives/unsafe-html.js"

/**
 * Custom event interface for hiding tool requests
 */
declare global {
  interface GlobalEventHandlersEventMap {
    "shiny-tool-request-hide": CustomEvent<{ request_id: string }>
  }
}

/**
 * Base class for tool-related card components
 */
class ShinyToolCard extends LitElement {
  @property({ type: String, attribute: "request-id" })
  requestId!: string

  @property({ type: String })
  name!: string

  @property({ type: String })
  title: string = ""

  @property({ type: String })
  intent?: string

  @property({ type: Boolean, reflect: true })
  expanded = false

  @property({ type: String })
  classStatus: string = ""

  @property({ type: String })
  icon: string = ""

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

  protected formatTitle() {
    let displayTitle = this.title || `${this.name}()`
    displayTitle = `<span class="tool-title-name">${displayTitle}</span>`
    displayTitle = this.titleTemplate.replace("{title}", displayTitle)
    return html`${unsafeHTML(displayTitle)}`
  }

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
        class="shiny-tool-card card bslib-card bslib-mb-spacing html-fill-item html-fill-container m-0"
        data-bslib-card-init
        data-require-bs-caller="chat_ui()"
        data-require-bs-version="5"
      >
        <button
          class="card-header"
          id="${headerId}"
          @click="${this.#toggleCollapse}"
          aria-expanded="${this.expanded}"
          aria-controls="${contentId}"
        >
          <div class="hstack gap-2">
            ${headerContent}
            <div class="collapse-arrow">◀</div>
          </div>
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
        <script data-bslib-card-init>
          bslib.Card.initializeAllCards()
        </script>
      </div>
    `
  }
}

/**
 * Web component that displays information about a tool request.
 *
 * @element shiny-tool-request
 */
export class ShinyToolRequest extends ShinyToolCard {
  @property({ type: String })
  arguments!: string

  @property({ type: Boolean, reflect: true })
  hidden = false

  constructor() {
    super()
    this.titleTemplate = "Running {title}"
    this.icon = '<div class="spinner-border" role="status"></div>'
  }

  connectedCallback() {
    super.connectedCallback()
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

    return this.renderCard(bodyContent)
  }
}

/**
 * Web component that displays the result of a tool execution.
 *
 * @element shiny-tool-result
 */
export class ShinyToolResult extends ShinyToolCard {
  @property({ type: String, attribute: "request-call" })
  requestCall?: string

  @property({ type: String })
  status!: string

  @property({ type: Boolean, attribute: "show-request" })
  showRequest = true

  @property({ type: String })
  value!: string

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
    } else {
      this.icon = ICONS.wrenchAdjustable
    }
    // Emit event to hide the corresponding tool request
    this.dispatchEvent(
      new CustomEvent("shiny-tool-request-hide", {
        detail: { request_id: this.requestId },
        bubbles: true,
        cancelable: true,
      }),
    )
  }

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
        result = markdownCodeBlock(this.value)
      }

      result = html`<shiny-markdown-stream
        content=${result || this.value}
        content-type="markdown"
        ?streaming=${false}
      ></shiny-markdown-stream>`
    }

    const resultHeader = this.showRequest
      ? html`<strong>Tool result</strong> `
      : ""

    return html`<div class="shiny-tool-result__result">
      ${resultHeader}${result}
    </div>`
  }

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
  tools: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-tools" viewBox="0 0 16 16">
  <path d="M1 0 0 1l2.2 3.081a1 1 0 0 0 .815.419h.07a1 1 0 0 1 .708.293l2.675 2.675-2.617 2.654A3.003 3.003 0 0 0 0 13a3 3 0 1 0 5.878-.851l2.654-2.617.968.968-.305.914a1 1 0 0 0 .242 1.023l3.27 3.27a.997.997 0 0 0 1.414 0l1.586-1.586a.997.997 0 0 0 0-1.414l-3.27-3.27a1 1 0 0 0-1.023-.242L10.5 9.5l-.96-.96 2.68-2.643A3.005 3.005 0 0 0 16 3q0-.405-.102-.777l-2.14 2.141L12 4l-.364-1.757L13.777.102a3 3 0 0 0-3.675 3.68L7.462 6.46 4.793 3.793a1 1 0 0 1-.293-.707v-.071a1 1 0 0 0-.419-.814zm9.646 10.646a.5.5 0 0 1 .708 0l2.914 2.915a.5.5 0 0 1-.707.707l-2.915-2.914a.5.5 0 0 1 0-.708M3 11l.471.242.529.026.287.445.445.287.026.529L5 13l-.242.471-.026.529-.445.287-.287.445-.529.026L3 15l-.471-.242L2 14.732l-.287-.445L1.268 14l-.026-.529L1 13l.242-.471.026-.529.445-.287.287-.445.529-.026z"/>
</svg>`,
  exclamationCircleFill: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-exclamation-circle-fill" viewBox="0 0 16 16">
  <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0M8 4a.905.905 0 0 0-.9.995l.35 3.507a.552.552 0 0 0 1.1 0l.35-3.507A.905.905 0 0 0 8 4m.002 6a1 1 0 1 0 0 2 1 1 0 0 0 0-2"/>
</svg>`,
  wrenchAdjustable: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-wrench-adjustable" viewBox="0 0 16 16">
  <path d="M16 4.5a4.5 4.5 0 0 1-1.703 3.526L13 5l2.959-1.11q.04.3.041.61"/>
  <path d="M11.5 9c.653 0 1.273-.139 1.833-.39L12 5.5 11 3l3.826-1.53A4.5 4.5 0 0 0 7.29 6.092l-6.116 5.096a2.583 2.583 0 1 0 3.638 3.638L9.908 8.71A4.5 4.5 0 0 0 11.5 9m-1.292-4.361-.596.893.809-.27a.25.25 0 0 1 .287.377l-.596.893.809-.27.158.475-1.5.5a.25.25 0 0 1-.287-.376l.596-.893-.809.27a.25.25 0 0 1-.287-.377l.596-.893-.809.27-.158-.475 1.5-.5a.25.25 0 0 1 .287.376M3 14a1 1 0 1 1 0-2 1 1 0 0 1 0 2"/>
</svg>`,
}

const markdownCodeBlock = (content: string, language: string = "markdown") => {
  const backticks = "`".repeat(8)
  return `${backticks}${language}\n${content}\n${backticks}`
}

declare global {
  interface HTMLElementTagNameMap {
    "shiny-tool-request": ShinyToolRequest
    "shiny-tool-result": ShinyToolResult
  }
}
