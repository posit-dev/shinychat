import { LitElement, html, css } from "lit"
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

  @property({ type: Boolean })
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
    let result = html``
    switch (this.value_type) {
      case "html":
        result = html`<div class="content-wrapper">
          ${unsafeHTML(this.value)}
        </div>`
        break
      case "code":
        result = html`<pre><code>${this.value}</code></pre>`
        break
      case "text":
        result = html`<div class="content-wrapper">${this.value}</div>`
        break
      case "markdown":
        result = html`<div class="content-wrapper">
          <shiny-markdown-stream
            content=${this.value}
            content-type="markdown"
            ?streaming=${false}
          ></shiny-markdown-stream>
        </div>`
        break
      default:
        result = html`<pre><code>${this.value}</code></pre>`
        break
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
      content="\`\`\`
${this.request_call}
\`\`\`"
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
    const detailsClass = `shiny-tool-result${this.status === "error" ? " failed" : ""}`

    let title = html`<span class="function-name"
      >${this.title ? this.title : this.name}</span
    >`
    if (this.status === "error") {
      title = html`Failed to call ${title}`
    } else if (!this.title) {
      title = html`Result from ${title}`
    }

    const intent = this.intent
      ? html` | <span class="intent">${this.intent}</span>`
      : ""

    return html`
      <div class=${detailsClass}>
        <details>
          <summary>${title}${intent}</summary>
          ${this.#renderRequest()}${this.#renderResult()}
        </details>
      </div>
    `
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "shiny-tool-request": ShinyToolRequest
    "shiny-tool-result": ShinyToolResult
  }
}
