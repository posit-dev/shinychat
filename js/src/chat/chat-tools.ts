import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { unsafeHTML } from 'lit/directives/unsafe-html.js';

/**
 * Web component that displays information about a tool request.
 * 
 * @element shiny-tool-request
 * 
 * @prop {string} id - Tool call ID
 * @prop {string} name - Tool name
 * @prop {string} title - Optional tool display title
 * @prop {string} intent - Optional tool intent
 * @prop {string} arguments - JSON string of tool arguments
 */
@customElement('shiny-tool-request')
export class ShinyToolRequest extends LitElement {
  @property({ type: String })
  id!: string;

  @property({ type: String })
  name!: string;

  @property({ type: String })
  title?: string;

  @property({ type: String })
  intent?: string;

  @property({ type: String })
  arguments!: string;

  static styles = css`
    :host {
      display: block;
    }

    .shiny-tool-request {
      margin: 0;
      border-radius: var(--bs-border-radius, 4px);
      overflow: hidden;
      padding: 0.5em;
      font-size: 0.8em;
      color: var(--bs-secondary, #6c757d);
      font-weight: 400;
      display: block;
      align-items: center;
      user-select: none;
    }

    .shiny-tool-request::before {
      content: "⬅";  /* UTF-8: \u2B05 */
      color: var(--bs-primary, #0d6efd);
      display: inline-block;
      margin-right: 0.5em;
      font-size: 1em;
      transform-origin: center;
      transform: rotateY(180deg);
    }

    /* Spacing rules matching the original CSS */
    :host(:not(:first-child)) .shiny-tool-request {
      margin-top: 1em;
    }

    :host(:not(:last-child)) .shiny-tool-request {
      margin-bottom: 1em;
    }

    /* Additional tool request specific styles */
    .function-name {
      font-weight: bold;
    }

    .intent {
      color: var(--bs-secondary, #6c757d);
      font-style: italic;
      margin-left: 0.5em;
    }

    .tool-arguments {
      display: none;  /* Hide by default as it wasn't in original */
    }
  `;

  render() {
    return html`
      <div class="shiny-tool-request">
        Running 
        <span class="function-name">${this.title || this.name}</span>
        ${this.intent ? html`<span class="intent">${this.intent}</span>` : ''}
      </div>
    `;
  }
}

/**
 * Web component that displays the result of a tool execution.
 * 
 * @element shiny-tool-result
 * 
 * @prop {string} id - Tool call ID from request
 * @prop {string} status - "success" or "error"
 * @prop {boolean} show_request - Whether to display the nested tool request
 * @prop {string} value - Content to display
 * @prop {string} value_type - "html", "markdown", "text", or "code"
 * @prop {string} title - Optional tool display title
 * @prop {string} intent - Optional tool intent
 */
@customElement('shiny-tool-result')
export class ShinyToolResult extends LitElement {
  @property({ type: String })
  id!: string;

  @property({ type: String })
  status!: string;

  @property({ type: Boolean })
  show_request = true;

  @property({ type: String })
  value!: string;

  @property({ type: String })
  value_type!: string;

  @property({ type: String })
  title?: string;

  @property({ type: String })
  intent?: string;

  static styles = css`
    :host {
      display: block;
    }

    .shiny-tool-result {
      margin: 0;
      border-radius: var(--bs-border-radius, 4px);
      overflow: hidden;
      padding: 0.5em;
      font-size: 0.8em;
    }

    details summary {
      padding: 1em;
      margin: -0.5em;
      margin-left: -1em;
      margin-top: -1em;
      color: var(--bs-secondary, #6c757d);
      font-weight: 400;
      cursor: pointer;
      display: block;
      align-items: center;
      user-select: none;
    }

    details summary::before {
      content: "✔";  /* UTF-8: \u2714 */
      color: var(--bs-success, #198754);
      display: inline-block;
      margin-right: 0.5em;
      font-size: 1em;
    }

    details.failed summary::before {
      content: "✘";  /* UTF-8: \u2718 */
      color: var(--bs-danger, #dc3545);
    }

    details[open] summary {
      margin-bottom: 1em;
      border-bottom: 1px solid var(--bs-border-color, #dee2e6);
    }

    details summary::marker,
    details summary::-webkit-details-marker {
      display: none;
    }

    details summary::after {
      display: inline-block;
      content: "◀";  /* UTF-8: \u25C0 */
      margin-left: 0.5em;
      font-size: 1em;
      transition: transform 0.2s;
    }

    details[open] summary::after {
      transform: rotate(-90deg);
    }

    details summary .function-name {
      font-weight: bold;
    }

    details summary .intent {
      color: var(--bs-secondary, #6c757d);
      font-style: italic;
    }

    /* Content styling */
    .content-wrapper {
      margin: 1em 0;
    }

    .content-wrapper :first-child {
      margin-top: 0;
    }

    .content-wrapper :last-child {
      margin-bottom: 0;
    }

    /* Code specific styling */
    pre {
      margin: 0;
      white-space: pre-wrap;
      background: var(--bs-gray-100, #f8f9fa);
      padding: 1em;
      border-radius: var(--bs-border-radius, 4px);
    }

    /* Spacing between adjacent components */
    :host(:not(:first-child)) .shiny-tool-result {
      margin-top: 1em;
    }

    :host(:not(:last-child)) .shiny-tool-result {
      margin-bottom: 1em;
    }
  `;

  private renderContent() {
    switch (this.value_type) {
      case 'html':
        return html`<div class="content-wrapper">${unsafeHTML(this.value)}</div>`;
      case 'code':
        return html`<pre><code>${this.value}</code></pre>`;
      case 'text':
        return html`<div class="content-wrapper">${this.value}</div>`;
      case 'markdown':
        // Note: Would need markdown-it or similar to render markdown
        return html`<div class="content-wrapper">${this.value}</div>`;
      default:
        return html`<pre><code>${this.value}</code></pre>`;
    }
  }

  render() {
    const detailsClass = `shiny-tool-result${this.status === 'error' ? ' failed' : ''}`;
    
    return html`
      <div class=${detailsClass}>
        <details ?open=${true}>
          <summary>
            ${this.status === 'error' ? 'Failed to call' : 'Result from'}
            <span class="function-name">${this.title || 'Tool'}</span>
            ${this.intent ? html`<span class="intent">${this.intent}</span>` : ''}
          </summary>

          ${this.show_request ? html`<slot></slot>` : ''}
          ${this.renderContent()}
        </details>
      </div>
    `;
  }
}

declare global {
  interface HTMLElementTagNameMap {
    'shiny-tool-request': ShinyToolRequest;
    'shiny-tool-result': ShinyToolResult;
  }
}
