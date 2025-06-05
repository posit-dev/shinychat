import { useState, useEffect, useRef, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import { MarkdownStream, ContentType } from "../../components/MarkdownStream"

const sampleMarkdown = `# MarkdownStream Demo

This is a **comprehensive** demonstration of the MarkdownStream component with various features:

## Text Formatting

- **Bold text**
- *Italic text*
- ~~Strikethrough text~~
- \`Inline code\`
- [Links](https://example.com)

## Lists

### Unordered List
- Item 1
- Item 2
  - Nested item A
  - Nested item B
- Item 3

### Ordered List
1. First item
2. Second item
3. Third item

## Code Blocks

### JavaScript
\`\`\`javascript
function fibonacci(n) {
  if (n <= 1) return n;
  return fibonacci(n - 1) + fibonacci(n - 2);
}

console.log("Fibonacci sequence:");
for (let i = 0; i < 10; i++) {
  console.log(\`F(\${i}) = \${fibonacci(i)}\`);
}
\`\`\`

### Python
\`\`\`python
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

# Calculate factorials
for i in range(1, 6):
    print(f"{i}! = {factorial(i)}")
\`\`\`

### SQL
\`\`\`sql
SELECT
    users.name,
    COUNT(orders.id) as order_count,
    SUM(orders.total) as total_spent
FROM users
LEFT JOIN orders ON users.id = orders.user_id
WHERE users.created_at >= '2024-01-01'
GROUP BY users.id, users.name
ORDER BY total_spent DESC;
\`\`\`

## Tables

| Language | Type | Year | Popularity |
|----------|------|------|------------|
| JavaScript | Dynamic | 1995 | ⭐⭐⭐⭐⭐ |
| Python | Dynamic | 1991 | ⭐⭐⭐⭐⭐ |
| TypeScript | Static | 2012 | ⭐⭐⭐⭐ |
| Rust | Static | 2010 | ⭐⭐⭐ |
| Go | Static | 2009 | ⭐⭐⭐⭐ |

## Blockquotes

> "The best way to predict the future is to invent it."
> — Alan Kay

> **Note:** This is a complex blockquote with **formatting** and \`code\`.

## Math and Special Characters

Mathematical symbols: α β γ δ ε ∑ ∫ ∞ ≈ ≠ ≤ ≥

Arrows: → ← ↑ ↓ ↔ ⇒ ⇔

Currency: $ € £ ¥ ₹ ₿

## Emojis and Unicode

🚀 🎉 🔥 ⭐ 💡 🎯 🌟 ✨ 🎨 🔧

Special characters: © ® ™ • § ¶ † ‡ ° ∞

## Final Notes

This demonstrates the full range of markdown features supported by the MarkdownStream component, including syntax highlighting, tables, and various text formatting options.
`

const sampleHTML = `
<div style="padding: 20px; border: 2px solid #007bff; border-radius: 8px; background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);">
  <h1 style="color: #007bff; margin-top: 0;">🌟 HTML Content Demo</h1>

  <p>This is <strong>HTML content</strong> with <em>inline styling</em> and <u>formatting</u>.</p>

  <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
    <div style="background: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
      <h3 style="margin-top: 0; color: #28a745;">✅ Features</h3>
      <ul style="list-style-type: none; padding: 0;">
        <li style="padding: 5px 0;">🎨 Rich styling</li>
        <li style="padding: 5px 0;">🔧 Custom elements</li>
        <li style="padding: 5px 0;">📱 Responsive design</li>
      </ul>
    </div>

    <div style="background: #fff; padding: 15px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
      <h3 style="margin-top: 0; color: #dc3545;">🔥 Code Example</h3>
      <pre style="background: #f8f9fa; padding: 10px; border-radius: 3px; overflow-x: auto;"><code class="language-html">&lt;div class="example"&gt;
  &lt;h1&gt;Hello World&lt;/h1&gt;
  &lt;p&gt;This is HTML!&lt;/p&gt;
&lt;/div&gt;</code></pre>
    </div>
  </div>

  <details style="margin: 20px 0;">
    <summary style="cursor: pointer; font-weight: bold; padding: 10px; background: #e9ecef; border-radius: 5px;">
      📋 Click to expand more details
    </summary>
    <div style="padding: 15px; background: #f8f9fa; border-radius: 0 0 5px 5px;">
      <p>This collapsible section demonstrates interactive HTML elements within the MarkdownStream component.</p>
      <button onclick="alert('Button clicked!')" style="background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer;">
        Click me! 🎯
      </button>
    </div>
  </details>

  <footer style="margin-top: 30px; padding-top: 20px; border-top: 1px solid #dee2e6; text-align: center; color: #6c757d;">
    <small>This HTML content showcases various styling capabilities 🎨</small>
  </footer>
</div>
`

const sampleText = `Plain Text Content Demo

This is plain text content that should be displayed exactly as typed.

No formatting will be applied:
- **This will show as asterisks**
- *This will show as asterisks*
- <strong>HTML tags will be escaped</strong>
- [Links](http://example.com) will show as-is

Special characters and symbols:
© ® ™ → ← ↑ ↓ ∞ ≈ ≠ ≤ ≥

Line breaks are preserved:

Multiple


Empty


Lines

Code blocks will not be formatted:
\`\`\`javascript
function example() {
  return "This is just plain text";
}
\`\`\`

Math symbols: α β γ δ ε ∑ ∫
Emojis: 🚀 🎉 🔥 ⭐ 💡

This mode is useful for displaying user input exactly as entered without any processing or security concerns.`

const sampleSemiMarkdown = `Semi-Markdown Demo

This content type allows **basic formatting** like *italics* and **bold** text, but HTML tags are escaped for security.

For example:
- **Bold text** works ✓
- *Italic text* works ✓
- <script>alert('xss')</script> is escaped ✓
- <div>HTML tags</div> are shown as text ✓

This is perfect for user-generated content where you want some formatting but need to prevent HTML injection.

Lists work:
1. First item
2. Second item
3. Third item

And so do links: [Example Link](https://example.com)

But complex HTML structures like <table><tr><td>tables</td></tr></table> are escaped and shown as text.

Code spans work: \`const example = "semi-markdown";\`

> Blockquotes also work normally

This provides a good balance between formatting and security! 🛡️`

interface StreamingDemo {
  title: string
  content: string
  contentType: ContentType
  description: string
}

const streamingDemos: StreamingDemo[] = [
  {
    title: "Full Markdown",
    content: sampleMarkdown,
    contentType: "markdown",
    description:
      "Complete markdown with code highlighting, tables, and formatting",
  },
  {
    title: "Rich HTML",
    content: sampleHTML,
    contentType: "html",
    description: "HTML content with custom styling and interactive elements",
  },
  {
    title: "Plain Text",
    content: sampleText,
    contentType: "text",
    description: "Raw text content without any formatting or processing",
  },
  {
    title: "Semi-Markdown",
    content: sampleSemiMarkdown,
    contentType: "semi-markdown",
    description: "Basic markdown with HTML escaping for user-generated content",
  },
]

export function MarkdownStreamDemo(): JSX.Element {
  const [currentDemo, setCurrentDemo] = useState<StreamingDemo>(
    streamingDemos[0] || {
      title: "Full Markdown",
      content: "",
      contentType: "markdown" as ContentType,
      description:
        "Complete markdown with code highlighting, tables, and formatting",
    },
  )
  const [content, setContent] = useState("")
  const [streaming, setStreaming] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)
  const [streamingSpeed, setStreamingSpeed] = useState(50)
  const [customContent, setCustomContent] = useState("")

  const [stats, setStats] = useState({
    contentChanges: 0,
    streamEnds: 0,
    lastUpdate: new Date().toLocaleTimeString(),
  })

  // Use a ref to track the current interval so we can clean it up
  const streamingIntervalRef = useRef<number | null>(null)

  // Simulate streaming by gradually adding content
  const simulateStreaming = useCallback(
    (targetContent: string, speed: number = streamingSpeed) => {
      // Clear any existing streaming interval
      if (streamingIntervalRef.current) {
        clearInterval(streamingIntervalRef.current)
        streamingIntervalRef.current = null
      }

      setContent("")
      setStreaming(true)
      setStats((prev) => ({
        ...prev,
        contentChanges: 0,
        streamEnds: prev.streamEnds,
      }))

      let currentIndex = 0

      streamingIntervalRef.current = window.setInterval(() => {
        if (currentIndex >= targetContent.length) {
          setStreaming(false)
          if (streamingIntervalRef.current) {
            clearInterval(streamingIntervalRef.current)
            streamingIntervalRef.current = null
          }
          return
        }

        // Add chunks of content to simulate realistic streaming
        const chunkSize = Math.floor(Math.random() * 15) + 1
        const nextChunk = targetContent.slice(
          currentIndex,
          currentIndex + chunkSize,
        )
        setContent((prev) => prev + nextChunk)
        currentIndex += chunkSize
      }, speed)
    },
    [streamingSpeed],
  )

  // Clean up interval on unmount
  useEffect(() => {
    return () => {
      if (streamingIntervalRef.current) {
        clearInterval(streamingIntervalRef.current)
      }
    }
  }, [])

  const handleContentChange = useCallback(() => {
    setStats((prev) => ({
      ...prev,
      contentChanges: prev.contentChanges + 1,
      lastUpdate: new Date().toLocaleTimeString(),
    }))
  }, [])

  const handleStreamEnd = useCallback(() => {
    setStats((prev) => ({
      ...prev,
      streamEnds: prev.streamEnds + 1,
      lastUpdate: new Date().toLocaleTimeString(),
    }))
  }, [])

  const loadDemo = useCallback(
    (demo: StreamingDemo) => {
      setCurrentDemo(demo)
      simulateStreaming(demo.content)
    },
    [simulateStreaming],
  )

  const loadCustomContent = useCallback(() => {
    if (customContent.trim()) {
      simulateStreaming(customContent)
    }
  }, [customContent, simulateStreaming])

  return (
    <div style={{ maxWidth: "1200px", margin: "0 auto", padding: "20px" }}>
      <header style={{ marginBottom: "30px", textAlign: "center" }}>
        <h1>🚀 MarkdownStream React Component</h1>
        <p
          style={{
            fontSize: "18px",
            color: "#666",
            maxWidth: "600px",
            margin: "0 auto",
          }}
        >
          A comprehensive demo showcasing streaming content rendering with
          syntax highlighting, auto-scrolling, and multiple content types.
        </p>
      </header>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 2fr",
          gap: "30px",
          marginBottom: "30px",
        }}
      >
        {/* Controls Panel */}
        <div
          style={{
            background: "#f8f9fa",
            padding: "20px",
            borderRadius: "8px",
            height: "fit-content",
          }}
        >
          <h2 style={{ marginTop: 0 }}>🎛️ Controls</h2>

          <div style={{ marginBottom: "20px" }}>
            <h3>Demo Content</h3>
            <div
              style={{ display: "flex", flexDirection: "column", gap: "8px" }}
            >
              {streamingDemos.map((demo, index) => (
                <button
                  key={index}
                  onClick={() => loadDemo(demo)}
                  style={{
                    padding: "10px",
                    textAlign: "left",
                    background: currentDemo === demo ? "#007bff" : "#fff",
                    color: currentDemo === demo ? "white" : "#333",
                    border: "1px solid #ddd",
                    borderRadius: "4px",
                    cursor: "pointer",
                  }}
                >
                  <strong>{demo.title}</strong>
                  <br />
                  <small>{demo.description}</small>
                </button>
              ))}
            </div>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <h3>Settings</h3>
            <div
              style={{ display: "flex", flexDirection: "column", gap: "10px" }}
            >
              <label
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <input
                  type="checkbox"
                  checked={autoScroll}
                  onChange={(e) =>
                    setAutoScroll((e.target as HTMLInputElement).checked)
                  }
                />
                <span>Auto Scroll</span>
              </label>

              <label
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                <input
                  type="checkbox"
                  checked={streaming}
                  onChange={(e) =>
                    setStreaming((e.target as HTMLInputElement).checked)
                  }
                />
                <span>Streaming (manual)</span>
              </label>

              <label
                style={{ display: "flex", flexDirection: "column", gap: "4px" }}
              >
                <span>Streaming Speed: {streamingSpeed}ms</span>
                <input
                  type="range"
                  min="10"
                  max="200"
                  value={streamingSpeed}
                  onChange={(e) =>
                    setStreamingSpeed(
                      Number((e.target as HTMLInputElement).value),
                    )
                  }
                />
              </label>
            </div>
          </div>

          <div style={{ marginBottom: "20px" }}>
            <h3>Custom Content</h3>
            <textarea
              value={customContent}
              onChange={(e) =>
                setCustomContent((e.target as HTMLTextAreaElement).value)
              }
              placeholder="Enter your own content to test..."
              style={{
                width: "100%",
                height: "100px",
                padding: "8px",
                borderRadius: "4px",
                border: "1px solid #ddd",
                fontFamily: "monospace",
                fontSize: "12px",
              }}
            />
            <button
              onClick={loadCustomContent}
              style={{
                marginTop: "8px",
                padding: "8px 16px",
                background: "#28a745",
                color: "white",
                border: "none",
                borderRadius: "4px",
                cursor: "pointer",
              }}
            >
              Stream Custom Content
            </button>
          </div>

          <div>
            <h3>📊 Stats</h3>
            <div style={{ fontSize: "14px", lineHeight: "1.6" }}>
              <div>
                <strong>Content Type:</strong> {currentDemo.contentType}
              </div>
              <div>
                <strong>Streaming:</strong>{" "}
                {streaming ? "🟢 Active" : "🔴 Inactive"}
              </div>
              <div>
                <strong>Auto Scroll:</strong> {autoScroll ? "✅ On" : "❌ Off"}
              </div>
              <div>
                <strong>Content Length:</strong>{" "}
                {content.length.toLocaleString()} chars
              </div>
              <div>
                <strong>Content Changes:</strong> {stats.contentChanges}
              </div>
              <div>
                <strong>Stream Ends:</strong> {stats.streamEnds}
              </div>
              <div>
                <strong>Last Update:</strong> {stats.lastUpdate}
              </div>
            </div>
          </div>
        </div>

        {/* Component Output */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "10px",
            }}
          >
            <h2 style={{ margin: 0 }}>📄 Component Output</h2>
            <div style={{ fontSize: "14px", color: "#666" }}>
              {streaming && (
                <span style={{ color: "#007bff" }}>🔄 Streaming...</span>
              )}
            </div>
          </div>

          <div
            style={{
              border: "2px solid #dee2e6",
              borderRadius: "8px",
              // minHeight: "400px",
              maxHeight: "600px",
              overflow: "auto",
              background: "#fff",
              position: "relative",
            }}
          >
            <MarkdownStream
              content={content}
              contentType={currentDemo.contentType}
              streaming={streaming}
              autoScroll={autoScroll}
              onContentChange={handleContentChange}
              onStreamEnd={handleStreamEnd}
            />

            {!content && (
              <div
                style={{
                  position: "absolute",
                  top: "50%",
                  left: "50%",
                  transform: "translate(-50%, -50%)",
                  color: "#999",
                  textAlign: "center",
                }}
              >
                <div style={{ fontSize: "48px", marginBottom: "16px" }}>📄</div>
                <div>
                  Select a demo above to see the MarkdownStream component in
                  action
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
