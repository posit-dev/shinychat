import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import {
  render,
  screen,
  cleanup,
  waitFor,
  fireEvent,
} from "@testing-library/preact"
import { MarkdownStream, ContentType } from "../MarkdownStream"
import { createTestContainer, cleanupTestContainer } from "./test-setup"

describe("MarkdownStream Integration Tests", () => {
  let testContainer: HTMLDivElement

  beforeEach(() => {
    vi.clearAllMocks()
    testContainer = createTestContainer()
  })

  afterEach(() => {
    cleanup()
    cleanupTestContainer(testContainer)
  })

  describe("Streaming Simulation", () => {
    it("handles progressive content updates correctly", async () => {
      const onContentChange = vi.fn()
      let content = "# Start"

      const { rerender } = render(
        <MarkdownStream
          content={content}
          contentType="markdown"
          streaming={true}
          onContentChange={onContentChange}
        />,
      )

      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Start",
      )
      expect(onContentChange).toHaveBeenCalledTimes(1)

      // Simulate streaming by adding more content
      content += "\n\nThis is **streaming** content."
      rerender(
        <MarkdownStream
          content={content}
          contentType="markdown"
          streaming={true}
          onContentChange={onContentChange}
        />,
      )

      expect(screen.getByText("streaming")).toBeInTheDocument()
      expect(onContentChange).toHaveBeenCalledTimes(2)

      // End streaming
      rerender(
        <MarkdownStream
          content={content}
          contentType="markdown"
          streaming={false}
          onContentChange={onContentChange}
        />,
      )

      // Streaming dot should be gone
      const container = document.querySelector(".markdown-stream")
      expect(container?.innerHTML).not.toContain("markdown-stream-dot")
    })

    it("maintains streaming dot during content updates", () => {
      const { rerender } = render(
        <MarkdownStream content="Initial" streaming={true} />,
      )

      let container = document.querySelector(".markdown-stream")
      expect(container?.innerHTML).toContain("markdown-stream-dot")

      rerender(
        <MarkdownStream content="Initial + More content" streaming={true} />,
      )

      container = document.querySelector(".markdown-stream")
      expect(container?.innerHTML).toContain("markdown-stream-dot")
    })
  })

  describe("Content Type Switching", () => {
    const testContent = "# Title\n\nThis is **bold** and <em>italic</em> text."

    it("renders differently for each content type", () => {
      const contentTypes: ContentType[] = [
        "markdown",
        "semi-markdown",
        "html",
        "text",
      ]

      contentTypes.forEach((contentType) => {
        const { unmount } = render(
          <MarkdownStream content={testContent} contentType={contentType} />,
        )

        const container = document.querySelector(".markdown-stream")
        expect(container).toBeInTheDocument()

        // Each content type should produce different HTML
        const html = container?.innerHTML || ""

        if (contentType === "text") {
          // Text should have the raw content with line breaks
          expect(html).toContain("# Title")
          expect(html).toContain("**bold**")
        } else if (contentType === "markdown") {
          // Markdown should process the heading and bold text
          expect(html).toContain("<h1>")
          expect(html).toContain("<strong>")
        }

        unmount()
      })
    })
  })

  describe("Code Highlighting Integration", () => {
    const codeContent = `
# Code Example

\`\`\`javascript
function hello(name) {
  console.log(\`Hello, \${name}!\`);
  return true;
}
\`\`\`

\`\`\`python
def greet(name):
    print(f"Hello, {name}!")
    return True
\`\`\`
    `.trim()

    it("processes multiple code blocks correctly", async () => {
      render(<MarkdownStream content={codeContent} contentType="markdown" />)

      await waitFor(() => {
        const codeBlocks = document.querySelectorAll("pre code")
        expect(codeBlocks.length).toBeGreaterThanOrEqual(2)
      })

      // Check that copy buttons are added
      const copyButtons = document.querySelectorAll(".code-copy-button")
      expect(copyButtons.length).toBeGreaterThanOrEqual(2)
    })

    it("handles code copy button functionality", async () => {
      render(<MarkdownStream content={codeContent} contentType="markdown" />)

      await waitFor(() => {
        const copyButton = document.querySelector(
          ".code-copy-button",
        ) as HTMLButtonElement
        expect(copyButton).toBeInTheDocument()

        // Simulate successful copy
        fireEvent.click(copyButton)

        // Note: We can't actually test clipboard functionality in jsdom,
        // but we can verify the button exists and is clickable
      })
    })
  })

  describe("Auto-scroll Behavior", () => {
    it("scrolls container when autoScroll is enabled", () => {
      const longContent = Array(50).fill("Line of content").join("\n\n")

      // Use default container instead of custom container to avoid cleanup issues
      const { container } = render(
        <MarkdownStream
          content={longContent}
          contentType="text"
          autoScroll={true}
        />,
      )

      // The actual scrolling behavior is complex to test in jsdom,
      // but we can verify the component renders without errors
      const markdownElement = container.querySelector(".markdown-stream")
      expect(markdownElement).toBeInTheDocument()

      // Verify that the content is actually long enough to require scrolling
      expect(markdownElement?.textContent?.length).toBeGreaterThan(100)
    })
  })

  describe("Table Rendering", () => {
    const tableMarkdown = `
| Column 1 | Column 2 | Column 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| More     | Data     | Here     |
    `.trim()

    it("renders markdown tables with Bootstrap classes", () => {
      render(<MarkdownStream content={tableMarkdown} contentType="markdown" />)

      const table = document.querySelector("table")
      expect(table).toBeInTheDocument()
      expect(table).toHaveClass("table", "table-striped", "table-bordered")

      const rows = document.querySelectorAll("tbody tr")
      expect(rows.length).toBe(2)

      const cells = document.querySelectorAll("td")
      expect(cells.length).toBe(6)
    })
  })

  describe("Error Handling", () => {
    it("handles malformed markdown gracefully", () => {
      const malformedMarkdown = "# Unclosed [link(\n\n**Unclosed bold"

      expect(() => {
        render(
          <MarkdownStream content={malformedMarkdown} contentType="markdown" />,
        )
      }).not.toThrow()

      const container = document.querySelector(".markdown-stream")
      expect(container).toBeInTheDocument()
    })

    it("handles very large content", () => {
      const largeContent =
        "# Large Content\n\n" + "Very long line of text. ".repeat(1000)

      expect(() => {
        render(<MarkdownStream content={largeContent} contentType="markdown" />)
      }).not.toThrow()

      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Large Content",
      )
    })

    it("handles special characters and emojis", () => {
      const specialContent =
        "# Special 🚀\n\nHere are emojis: 🎉 🔥 ⭐\n\nAnd symbols: © ® ™ → ←"

      render(<MarkdownStream content={specialContent} contentType="markdown" />)

      expect(screen.getByText("🚀", { exact: false })).toBeInTheDocument()
      expect(screen.getByText("🎉", { exact: false })).toBeInTheDocument()
    })
  })
})
