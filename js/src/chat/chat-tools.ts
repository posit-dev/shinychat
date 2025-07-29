import { LitElement, html, css, TemplateResult } from "lit"
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
 * Web component that displays information about a tool request.
 *
 * @element shiny-tool-request
 *
 * @prop {string} request_id - Tool call ID
 * @prop {string} name - Tool name
 * @prop {string} title - Optional tool display title
 * @prop {string} intent - Optional tool intent
 * @prop {string} arguments - JSON string of tool arguments
 * @prop {boolean} hidden - Whether the element should be hidden
 */

export class ShinyToolRequest extends LitElement {
  @property({ type: String })
  request_id!: string

  @property({ type: String })
  name!: string

  @property({ type: String })
  title: string = ""

  @property({ type: String })
  intent?: string

  @property({ type: String })
  arguments!: string

  @property({ type: Boolean, reflect: true })
  hidden = false

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
    if (event.detail.request_id === this.request_id) {
      this.hidden = true
    }
  }

  createRenderRoot(): ShinyToolRequest {
    return this
  }

  render() {
    if (this.hidden) {
      return html``
    }

    return html`
      <div class="shiny-tool-request">
        Running
        <span class="function-name">${this.title || this.name}</span>
        ${this.intent ? html`<span class="intent">${this.intent}</span>` : ""}
      </div>
    `
  }
}

/**
 * Web component that displays the result of a tool execution.
 *
 * @element shiny-tool-result
 *
 * @prop {string} request_id - Tool call ID from request
 * @prop {string} request_call - Optional tool call string
 * @prop {string} status - "success" or "error"
 * @prop {boolean} show_request - Whether to display the nested tool request
 * @prop {string} value - Content to display
 * @prop {string} value_type - "html", "markdown", "text", or "code"
 * @prop {string} name - Tool name
 * @prop {string} title - Optional tool display title
 * @prop {string} intent - Optional tool intent
 */
export class ShinyToolResult extends LitElement {
  @property({ type: String })
  request_id!: string

  @property({ type: String })
  request_call?: string

  @property({ type: String })
  status!: string

  @property({ type: Boolean })
  show_request = true

  @property({ type: String })
  value!: string

  @property({ type: String })
  value_type!: string

  @property({ type: String })
  title: string = ""

  @property({ type: String })
  name: string = ""

  @property({ type: String })
  intent?: string

  @property({ type: Boolean, reflect: true })
  expanded = false

  connectedCallback() {
    super.connectedCallback()
    // Emit event to hide the corresponding tool request
    this.dispatchEvent(
      new CustomEvent("shiny-tool-request-hide", {
        detail: { request_id: this.request_id },
        bubbles: true,
        cancelable: true,
      }),
    )
  }

  #renderResult() {
    let result: string | TemplateResult = ""

    if (this.value_type === "html") {
      result = html`${unsafeHTML(this.value)}`
    } else if (this.value_type === "text") {
      result = html`<p>${this.value}</p>`
    } else {
      // markdown, code, or default
      if (this.value_type !== "markdown") {
        // If value_type is "code", we format it as a markdown code block
        const backticks = "`".repeat(8)
        result = `${backticks}markdown\n${this.value}\n${backticks}`
      }

      result = html`<shiny-markdown-stream
        content=${result || this.value}
        content-type="markdown"
        ?streaming=${false}
      ></shiny-markdown-stream>`
    }

    return html`<div class="shiny-tool-result__result">
      <strong>Tool result</strong> ${result}
    </div>`
  }

  #renderRequest() {
    if (!this.show_request || !this.request_call) {
      return ""
    }

    const request = html`<shiny-markdown-stream
      content="${"`".repeat(8)}
${this.request_call}
${"`".repeat(8)}"
      content-type="markdown"
      ?streaming=${false}
    ></shiny-markdown-stream>`

    const isLongRequest = this.request_call.split("\n").length > 2

    return html`<div class="shiny-tool-result__request">
      ${isLongRequest
        ? html`<details>
            <summary>Tool call</summary>
            ${request}
          </details>`
        : html`<strong>Tool call</strong> ${request}`}
    </div>`
  }

  createRenderRoot(): ShinyToolResult {
    return this
  }

  render() {
    const headerId = `tool-header-${this.request_id}`
    const contentId = `tool-content-${this.request_id}`
    const statusIcon =
      this.status === "error" ? ICONS.exclamationCircleFill : ICONS.tools

    let title = html`<span class="function-name"
      >${this.title ? this.title : this.name + "()"}</span
    >`
    if (this.status === "error") {
      title = html`${title} failed`
    }

    const statusClass = this.status === "error" ? "text-danger" : ""

    return html`
      <div
        class="card bslib-card bslib-mb-spacing html-fill-item html-fill-container m-0"
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
            <div class="tool-icon ${statusClass}">
              ${unsafeHTML(statusIcon)}
            </div>
            <div class="request-title ${statusClass}">${title}</div>
            <div class="request-intent">${this.intent || ""}</div>
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
          ${this.#renderRequest()} ${this.#renderResult()}
        </div>
        <script data-bslib-card-init>
          bslib.Card.initializeAllCards()
        </script>
      </div>
    `
  }

  #toggleCollapse(e: Event) {
    e.preventDefault()
    this.expanded = !this.expanded
    this.requestUpdate()
  }
}

const ICONS = {
  tools: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-tools" viewBox="0 0 16 16">
  <path d="M1 0 0 1l2.2 3.081a1 1 0 0 0 .815.419h.07a1 1 0 0 1 .708.293l2.675 2.675-2.617 2.654A3.003 3.003 0 0 0 0 13a3 3 0 1 0 5.878-.851l2.654-2.617.968.968-.305.914a1 1 0 0 0 .242 1.023l3.27 3.27a.997.997 0 0 0 1.414 0l1.586-1.586a.997.997 0 0 0 0-1.414l-3.27-3.27a1 1 0 0 0-1.023-.242L10.5 9.5l-.96-.96 2.68-2.643A3.005 3.005 0 0 0 16 3q0-.405-.102-.777l-2.14 2.141L12 4l-.364-1.757L13.777.102a3 3 0 0 0-3.675 3.68L7.462 6.46 4.793 3.793a1 1 0 0 1-.293-.707v-.071a1 1 0 0 0-.419-.814zm9.646 10.646a.5.5 0 0 1 .708 0l2.914 2.915a.5.5 0 0 1-.707.707l-2.915-2.914a.5.5 0 0 1 0-.708M3 11l.471.242.529.026.287.445.445.287.026.529L5 13l-.242.471-.026.529-.445.287-.287.445-.529.026L3 15l-.471-.242L2 14.732l-.287-.445L1.268 14l-.026-.529L1 13l.242-.471.026-.529.445-.287.287-.445.529-.026z"/>
</svg>`,
  exclamationCircleFill: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-exclamation-circle-fill" viewBox="0 0 16 16">
  <path d="M16 8A8 8 0 1 1 0 8a8 8 0 0 1 16 0M8 4a.905.905 0 0 0-.9.995l.35 3.507a.552.552 0 0 0 1.1 0l.35-3.507A.905.905 0 0 0 8 4m.002 6a1 1 0 1 0 0 2 1 1 0 0 0 0-2"/>
</svg>`,
}

declare global {
  interface HTMLElementTagNameMap {
    "shiny-tool-request": ShinyToolRequest
    "shiny-tool-result": ShinyToolResult
  }
}
