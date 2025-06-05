import { render } from "preact"
import { MarkdownStreamDemo } from "./MarkdownStreamDemo"

export function renderDemo(): void {
  const rootElement = document.getElementById("root")
  if (!rootElement) {
    console.error("Root element not found")
    return
  }

  try {
    render(<MarkdownStreamDemo />, rootElement)
    console.log("MarkdownStreamDemo rendered successfully")
  } catch (error) {
    console.error("Error rendering demo:", error)
    rootElement.innerHTML = `
      <div style="padding: 20px; color: #dc3545; text-align: center;">
        <h1>Demo Error</h1>
        <p>Failed to load the MarkdownStream demo.</p>
        <pre>${error}</pre>
      </div>
    `
  }
}

// Auto-render when DOM is ready
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderDemo)
  } else {
    // DOM is already loaded
    renderDemo()
  }
}

export { renderDemo as render }
