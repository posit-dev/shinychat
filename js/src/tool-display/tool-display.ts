import { html, TemplateResult } from "lit"
import { unsafeHTML } from "lit-html/directives/unsafe-html.js"
import { property } from "lit/decorators.js"

import { escapeHTML, hasProperty, LightElement } from "../utils/_utils"

const REQUEST_TAG_NAME = "shinychat-tool-request"
const RESULT_TAG_NAME = "shinychat-tool-result"

class ToolRequest extends LightElement {
  @property({ type: String, attribute: "data-tool-call-id" }) toolCallId = ""
  @property({ type: String }) name = ""

  render() {
    return html`Running tool: <code>${this.name}</code>`
  }
}

class ToolResult extends LightElement {
  // Props are strings so they can be set via HTML attributes,
  // but props that default to "{}" are expected to be JSON strings.
  @property({ type: String, attribute: "data-tool-call-id" }) toolCallId = ""
  @property({ type: String }) name = ""
  @property({ type: String }) arguments = "{}"
  @property({ type: String }) value = ""
  @property({ type: String }) error = ""
  // https://modelcontextprotocol.io/docs/concepts/tools#tool-annotations
  @property({ type: String }) annotations = "{}"

  get parsedArguments() {
    return parseAttrToObject(this.arguments, "arguments")
  }

  get parsedAnnotations() {
    return parseAttrToObject(this.annotations, "annotations")
  }

  connectedCallback(): void {
    super.connectedCallback()
    this.hideCorrespondingRequest()
  }

  private hideCorrespondingRequest(): void {
    const requestEl = document.querySelector<HTMLElement>(
      `${REQUEST_TAG_NAME}[data-tool-call-id="${this.toolCallId}"]`,
    )
    if (requestEl) {
      requestEl.style.display = "none"
    }
  }

  render(): TemplateResult {
    // Prepare result and parameters
    const result = this.error || this.value || "No result"
    const renderedResult = this.renderCodeBlock(result)
    const renderedParams = this.renderParameters()

    // N.B., we manually escape the input parameters, result, and tool name
    return html`<details>
      ${unsafeHTML(this.renderMainSummary())}
      <div class="result-container">
        <details open>
          <summary><strong>Result:</strong></summary>
          ${unsafeHTML(renderedResult)}
        </details>
        ${unsafeHTML(renderedParams)}
      </div>
    </details>`
  }

  // Markup for the top-level summary
  private renderMainSummary(): string {
    const name = escapeHTML(this.name)
    let content = `Tool <code>${name}</code> result`
    if (hasProperty(this.parsedAnnotations, "title")) {
      content = this.parsedAnnotations.title as string
    }
    if (this.error) {
      content = `Tool <code>${name}</code> failed`
    }

    let cssClass = "result-summary"
    if (this.error) {
      cssClass += " failed"
    }

    return `<summary class="${cssClass}">${content}</summary>`
  }

  private renderParameters(): string {
    const args = this.parsedArguments
    if (!args) {
      return ""
    }

    const formattedArgs = Object.entries(args)
      .map(([key, value]) => this.renderCodeBlock(String(value), key))
      .join("")

    return `
      <details open>
        <summary><strong>Input parameters:</strong></summary>
        ${formattedArgs}
      </details>`
  }

  private renderCodeBlock(code: string, label?: string): string {
    const labelSpan = label
      ? `<span class='input-parameter-label'>${label}</span>`
      : ""
    return `<pre>${labelSpan}<code>${escapeHTML(code)}</code></pre>`
  }
}

// ----------------- Utility functions -----------------------------------

type ParsedObjectAttr = {
  [key: string]: unknown
}

function parseAttrToObject(x: string, name: string): ParsedObjectAttr {
  try {
    return JSON.parse(x) as ParsedObjectAttr
  } catch (e) {
    console.error(`Failed to parse ${name} JSON:`, e)
    return {}
  }
}

if (!customElements.get(REQUEST_TAG_NAME)) {
  customElements.define(REQUEST_TAG_NAME, ToolRequest)
}
if (!customElements.get(RESULT_TAG_NAME)) {
  customElements.define(RESULT_TAG_NAME, ToolResult)
}

// TODO: why does this error?
//export { ToolRequest, ToolResult }
