import { render } from "preact"
import { ChatDemo } from "./ChatDemo"

// Render the demo when the DOM is ready
document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("demo-root")
  if (container) {
    render(<ChatDemo />, container)
  }
})
