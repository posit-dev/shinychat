// Import the Shiny integration
import "../../components/ShinyMarkdownStream"
import type {
  ContentMessage,
  IsStreamingMessage,
} from "../../components/ShinyMarkdownStream"

// Mock Shiny object for testing
declare global {
  interface Window {
    Shiny: {
      addCustomMessageHandler: (
        type: string,
        handler: (message: ContentMessage | IsStreamingMessage) => void,
      ) => void
      setInputValue: (inputId: string, value: unknown) => void
    }
    shinyHandlers: Record<
      string,
      (message: ContentMessage | IsStreamingMessage) => void
    >
  }
}

// Initialize mock Shiny
window.Shiny = {
  addCustomMessageHandler: function (
    type: string,
    handler: (message: ContentMessage | IsStreamingMessage) => void,
  ) {
    console.log(`Registered handler for: ${type}`)
    window.shinyHandlers = window.shinyHandlers || {}
    window.shinyHandlers[type] = handler
  },
  setInputValue: function (inputId: string, value: unknown) {
    console.log(`Setting input ${inputId}:`, value)
  },
}

// Helper function to send messages to our handler
function sendShinyMessage(message: ContentMessage | IsStreamingMessage) {
  const handler = window.shinyHandlers?.shinyMarkdownStreamMessage
  if (handler) {
    handler(message)
    const statusEl = document.getElementById("status")
    if (statusEl) {
      statusEl.innerText = `Sent: ${JSON.stringify(message)}`
    }
  } else {
    console.error("Handler not found")
  }
}

// Demo functions
function replaceContent() {
  sendShinyMessage({
    id: "demo-markdown-stream",
    content:
      '# New Content\n\nThis content **replaces** the previous content.\n\n```javascript\nconsole.log("Hello, world!");\n```',
    operation: "replace",
  })
}

function appendContent() {
  sendShinyMessage({
    id: "demo-markdown-stream",
    content:
      "\n\n## Appended Section\n\nThis content is *appended* to the existing content.",
    operation: "append",
  })
}

function toggleStreaming() {
  const el = document.getElementById("demo-markdown-stream")
  const isStreaming = el?.hasAttribute("streaming")
  sendShinyMessage({
    id: "demo-markdown-stream",
    isStreaming: !isStreaming,
  })
}

function setMarkdown() {
  const el = document.getElementById("demo-markdown-stream")
  el?.setAttribute("content-type", "markdown")
  sendShinyMessage({
    id: "demo-markdown-stream",
    content:
      "# Markdown Content\n\nThis is **bold** and *italic* text.\n\n- List item 1\n- List item 2\n- List item 3",
    operation: "replace",
  })
}

function setHTML() {
  const el = document.getElementById("demo-markdown-stream")
  el?.setAttribute("content-type", "html")
  sendShinyMessage({
    id: "demo-markdown-stream",
    content:
      "<h1>HTML Content</h1><p>This is <strong>raw HTML</strong> content.</p><ul><li>Item 1</li><li>Item 2</li></ul>",
    operation: "replace",
  })
}

function clearContent() {
  sendShinyMessage({
    id: "demo-markdown-stream",
    content: "",
    operation: "replace",
  })
}

// Attach functions to window for HTML buttons
Object.assign(window, {
  replaceContent,
  appendContent,
  toggleStreaming,
  setMarkdown,
  setHTML,
  clearContent,
})

// Set up initial demo content
document.addEventListener("DOMContentLoaded", () => {
  // Create demo HTML structure
  const container = document.createElement("div")
  container.className = "container"
  container.innerHTML = `
    <h1>Shiny MarkdownStream Demo</h1>
    <p>This demo shows the React-based MarkdownStream component working with Shiny-style messaging.</p>

    <div class="controls">
        <h3>Controls</h3>
        <button onclick="replaceContent()">Replace Content</button>
        <button onclick="appendContent()">Append Content</button>
        <button onclick="toggleStreaming()">Toggle Streaming</button>
        <button onclick="setMarkdown()">Set Markdown</button>
        <button onclick="setHTML()">Set HTML</button>
        <button onclick="clearContent()">Clear</button>
    </div>

    <div class="demo-output">
        <shiny-markdown-stream
            id="demo-markdown-stream"
            content="# Welcome to MarkdownStream\n\nThis is the initial content."
            content-type="markdown"
            auto-scroll>
        </shiny-markdown-stream>
    </div>

    <div class="status" id="status">
        Ready
    </div>
  `

  // Add basic styles
  const style = document.createElement("style")
  style.textContent = `
    body {
        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        margin: 2rem;
        line-height: 1.6;
    }
    .container {
        max-width: 800px;
        margin: 0 auto;
    }
    .controls {
        margin-bottom: 2rem;
        padding: 1rem;
        background: #f5f5f5;
        border-radius: 8px;
    }
    .controls button {
        margin: 0.5rem 0.5rem 0.5rem 0;
        padding: 0.5rem 1rem;
        background: #007bff;
        color: white;
        border: none;
        border-radius: 4px;
        cursor: pointer;
    }
    .controls button:hover {
        background: #0056b3;
    }
    .demo-output {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 1rem;
        min-height: 200px;
        background: white;
    }
    .status {
        margin-top: 1rem;
        padding: 0.5rem;
        background: #e9ecef;
        border-radius: 4px;
        font-size: 0.9em;
    }
  `

  document.head.appendChild(style)
  document.body.appendChild(container)
})
