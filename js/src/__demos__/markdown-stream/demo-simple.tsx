import { render } from "preact"
import { MarkdownStream } from "../../components/MarkdownStream"

const testMarkdown = `# Test

This is a **simple** test of the MarkdownStream component.

## Code Example

\`\`\`javascript
console.log('Hello, world!')
console.log('This is a test')
\`\`\`

## List Example

- Item 1
- Item 2
- Item 3

## Table Example

| Column 1 | Column 2 |
|----------|----------|
| Value 1  | Value 2  |
| Value 3  | Value 4  |
`

function SimpleDemo() {
  return (
    <div style={{ padding: "20px", maxWidth: "800px", margin: "0 auto" }}>
      <h1>Simple MarkdownStream Test</h1>
      <div
        style={{
          border: "1px solid #ccc",
          padding: "20px",
          borderRadius: "8px",
        }}
      >
        <MarkdownStream
          content={testMarkdown}
          contentType="markdown"
          streaming={false}
          autoScroll={false}
        />
      </div>
    </div>
  )
}

export function renderSimpleDemo(): void {
  const rootElement = document.getElementById("root")
  if (!rootElement) {
    console.error("Root element not found")
    return
  }

  try {
    render(<SimpleDemo />, rootElement)
    console.log("Simple demo rendered successfully")
  } catch (error) {
    console.error("Error rendering simple demo:", error)
    rootElement.innerHTML = `
      <div style="padding: 20px; color: #dc3545; text-align: center;">
        <h1>Demo Error</h1>
        <p>Failed to load the simple demo.</p>
        <pre>${error}</pre>
      </div>
    `
  }
}

// Auto-render when DOM is ready
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", renderSimpleDemo)
  } else {
    renderSimpleDemo()
  }
}

export { renderSimpleDemo as render }
