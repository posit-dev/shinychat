import { describe, it, expect, vi, beforeEach } from "vitest"
import { render } from "@testing-library/react"
import * as markdownToReactModule from "../../src/markdown/markdownToReact"
import { MarkdownContent } from "../../src/markdown/MarkdownContent"

// MarkdownContent is a pure component — it does NOT call useShinyLifecycle,
// so no context wrapper is needed.

describe("MarkdownContent (pure)", () => {
  it("renders markdown as React elements (bold)", () => {
    const { container } = render(
      <MarkdownContent content="**bold**" contentType="markdown" />,
    )
    expect(container.querySelector("strong")).not.toBeNull()
  })

  it("renders plain text when contentType=text (no markdown processing)", () => {
    const { container } = render(
      <MarkdownContent content="**not bold**" contentType="text" />,
    )
    // Should render as literal text, not a <strong> tag
    expect(container.querySelector("strong")).toBeNull()
    expect(container.textContent).toContain("**not bold**")
  })

  it("renders empty content without errors", () => {
    const { container } = render(
      <MarkdownContent content="" contentType="markdown" />,
    )
    expect(container).toBeTruthy()
  })

  it("does NOT call bindAll or unbindAll (no Shiny side effects)", () => {
    // The pure MarkdownContent should not import or use useShinyLifecycle.
    // We verify by checking no context is consumed: if it tried to use the
    // context without a provider it would throw. Rendering without a provider
    // proves it doesn't call useShinyLifecycle.
    expect(() => {
      render(<MarkdownContent content="hello" contentType="markdown" />)
    }).not.toThrow()
  })

  it("renders tool tags without requiring chat contexts", () => {
    const content =
      '<shiny-tool-result request-id="req-1" tool-name="get_weather" status="success" value="Sunny" value-type="text"></shiny-tool-result>'

    expect(() => {
      render(<MarkdownContent content={content} contentType="markdown" />)
    }).not.toThrow()
  })

  it("shows streaming dot when streaming=true", () => {
    const { container } = render(
      <MarkdownContent
        content="hello"
        contentType="markdown"
        streaming={true}
      />,
    )
    expect(container.querySelector(".markdown-stream-dot")).not.toBeNull()
  })

  it("hides streaming dot when streaming=false", () => {
    const { container } = render(
      <MarkdownContent
        content="hello"
        contentType="markdown"
        streaming={false}
      />,
    )
    expect(container.querySelector(".markdown-stream-dot")).toBeNull()
  })

  it("does not re-run parseMarkdown when only streaming changes", () => {
    const spy = vi.spyOn(markdownToReactModule, "parseMarkdown")

    const { rerender } = render(
      <MarkdownContent
        content="hello"
        contentType="markdown"
        streaming={true}
      />,
    )

    const callCount = spy.mock.calls.length

    // Toggle streaming — parseMarkdown should NOT be called again
    rerender(
      <MarkdownContent
        content="hello"
        contentType="markdown"
        streaming={false}
      />,
    )

    expect(spy.mock.calls.length).toBe(callCount)

    spy.mockRestore()
  })
})
