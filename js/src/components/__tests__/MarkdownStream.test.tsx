import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, cleanup } from "@testing-library/preact"
import { MarkdownStream, ContentType } from "../MarkdownStream"

// Mock clipboard
vi.mock("clipboard", () => {
  return {
    default: vi.fn().mockImplementation(() => ({
      on: vi.fn(),
      destroy: vi.fn(),
    })),
  }
})

// Mock highlight.js
vi.mock("highlight.js/lib/common", () => {
  return {
    default: {
      highlightElement: vi.fn((el) => {
        el.dataset.highlighted = "yes"
      }),
    },
  }
})

describe("MarkdownStream", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  describe("Content Rendering", () => {
    it("renders markdown content correctly", () => {
      const markdownContent = "# Hello\n\nThis is **bold** text."

      render(
        <MarkdownStream content={markdownContent} contentType="markdown" />,
      )

      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "Hello",
      )
      expect(screen.getByText("bold")).toBeInTheDocument()
    })

    it("renders HTML content correctly", () => {
      const htmlContent =
        "<h1>HTML Title</h1><p>HTML <strong>content</strong></p>"

      render(<MarkdownStream content={htmlContent} contentType="html" />)

      expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
        "HTML Title",
      )
      expect(screen.getByText("content")).toBeInTheDocument()
    })

    it("renders text content correctly", () => {
      const textContent = "Plain text\nwith line breaks"

      render(<MarkdownStream content={textContent} contentType="text" />)

      // Text content should be rendered with <br> tags for line breaks
      const container = document.querySelector(".markdown-stream")
      expect(container).toBeInTheDocument()

      // Check that both parts of the text are present
      expect(container).toHaveTextContent("Plain text")
      expect(container).toHaveTextContent("with line breaks")

      // Check that <br> tag is present for line break
      expect(container?.innerHTML).toContain("<br>")
    })

    it("renders semi-markdown content correctly", () => {
      const semiMarkdownContent = "This is **bold** and <tag>escaped</tag>"

      render(
        <MarkdownStream
          content={semiMarkdownContent}
          contentType="semi-markdown"
        />,
      )

      expect(screen.getByText("bold")).toBeInTheDocument()
      // HTML tags should be escaped in semi-markdown
      expect(
        screen.getByText("<tag>escaped</tag>", { exact: false }),
      ).toBeInTheDocument()
    })
  })

  describe("Streaming State", () => {
    it("shows streaming dot when streaming is true", () => {
      render(<MarkdownStream content="Test content" streaming={true} />)

      const container = document.querySelector(".markdown-stream")
      expect(container?.innerHTML).toContain("markdown-stream-dot")
    })

    it("does not show streaming dot when streaming is false", () => {
      render(<MarkdownStream content="Test content" streaming={false} />)

      const container = document.querySelector(".markdown-stream")
      expect(container?.innerHTML).not.toContain("markdown-stream-dot")
    })

    it("calls onStreamEnd when streaming changes from true to false", () => {
      const onStreamEnd = vi.fn()

      const { rerender } = render(
        <MarkdownStream
          content="Test content"
          streaming={true}
          onStreamEnd={onStreamEnd}
        />,
      )

      expect(onStreamEnd).not.toHaveBeenCalled()

      rerender(
        <MarkdownStream
          content="Test content"
          streaming={false}
          onStreamEnd={onStreamEnd}
        />,
      )

      expect(onStreamEnd).toHaveBeenCalledTimes(1)
    })
  })

  describe("Content Changes", () => {
    it("calls onContentChange when content updates", () => {
      const onContentChange = vi.fn()

      const { rerender } = render(
        <MarkdownStream
          content="Initial content"
          onContentChange={onContentChange}
        />,
      )

      // Should be called once for initial render
      expect(onContentChange).toHaveBeenCalledTimes(1)

      rerender(
        <MarkdownStream
          content="Updated content"
          onContentChange={onContentChange}
        />,
      )

      // Should be called again for content update
      expect(onContentChange).toHaveBeenCalledTimes(2)
    })

    it("handles content type changes", () => {
      const { rerender } = render(
        <MarkdownStream content="**Bold text**" contentType="markdown" />,
      )

      expect(screen.getByText("Bold text")).toBeInTheDocument()

      rerender(<MarkdownStream content="**Bold text**" contentType="text" />)

      // In text mode, asterisks should be visible
      expect(screen.getByText("**Bold text**")).toBeInTheDocument()
    })
  })

  describe("Code Highlighting", () => {
    it("processes code blocks for syntax highlighting", () => {
      const codeContent =
        "```javascript\nfunction test() {\n  return 'hello';\n}\n```"

      render(<MarkdownStream content={codeContent} contentType="markdown" />)

      // Should have code element
      const codeElement = document.querySelector("pre code")
      expect(codeElement).toBeInTheDocument()
    })
  })

  describe("Props Handling", () => {
    it("uses default contentType when not specified", () => {
      render(<MarkdownStream content="# Default" />)

      expect(screen.getByRole("heading", { level: 1 })).toBeInTheDocument()
    })

    it("handles empty content", () => {
      render(<MarkdownStream content="" />)

      const container = document.querySelector(".markdown-stream")
      expect(container).toBeInTheDocument()
      expect(container).toBeEmptyDOMElement()
    })

    it("applies data attributes correctly", () => {
      render(<MarkdownStream content="Test" streaming={true} />)

      const container = document.querySelector(".markdown-stream")
      expect(container).toHaveAttribute("data-streaming", "true")
    })
  })

  describe("Error Handling", () => {
    it("throws error for invalid content type", () => {
      // Invalid content types should throw an error (intentional behavior)
      expect(() => {
        render(
          <MarkdownStream
            content="Test content"
            contentType={"invalid" as ContentType}
          />,
        )
      }).toThrow("Unknown content type: invalid")
    })

    it("handles callback errors gracefully", () => {
      const consoleWarnSpy = vi
        .spyOn(console, "warn")
        .mockImplementation(() => {})
      const faultyCallback = vi.fn().mockImplementation(() => {
        throw new Error("Callback error")
      })

      expect(() => {
        render(
          <MarkdownStream
            content="Test content"
            onContentChange={faultyCallback}
          />,
        )
      }).not.toThrow()

      expect(consoleWarnSpy).toHaveBeenCalled()
      consoleWarnSpy.mockRestore()
    })
  })
})
