import { render } from "preact"
import { HelloWorld } from "./HelloWorld"

export class ShinyHelloWorld extends HTMLElement {
  connectedCallback() {
    // Don't use shadow DOM so the component can inherit styles from the main document
    const name = this.getAttribute("data-name") || "World"

    render(<HelloWorld name={name} />, this)
  }

  disconnectedCallback() {
    // Clean up when element is removed
    render(null, this)
  }
}

customElements.define("shiny-hello-world", ShinyHelloWorld)
