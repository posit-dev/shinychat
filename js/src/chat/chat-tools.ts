import { LitElement, html, css } from 'lit';
import { customElement, property } from 'lit/decorators.js';

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

declare global {
  interface HTMLElementTagNameMap {
    'shiny-tool-request': ShinyToolRequest;
  }
}
