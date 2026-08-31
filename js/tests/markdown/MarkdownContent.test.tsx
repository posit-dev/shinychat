import { describe, it, expect, vi, beforeEach } from "vitest"
import { fireEvent, render, screen, within } from "@testing-library/react"
import * as markdownToReactModule from "../../src/markdown/markdownToReact"
import { MarkdownContent } from "../../src/markdown/MarkdownContent"
import { EscapedIsland } from "../../src/markdown/EscapedIsland"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"

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

  it("renders raw HTML when contentType=html", () => {
    const { container } = render(
      <MarkdownContent
        content={'<div class="custom-html">**not bold**</div><span>tail</span>'}
        contentType="html"
      />,
    )

    expect(container.querySelector(".custom-html")).not.toBeNull()
    expect(container.querySelector("strong")).toBeNull()
    expect(container.textContent).toContain("**not bold**")
    expect(container.textContent).toContain("tail")
  })

  it("groups a <shiny-aside> tag in html content into an aside pill", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<p>A claim<shiny-aside label="Source" url="https://x.example"></shiny-aside>.</p>'
        }
        contentType="html"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.querySelector(".shiny-aside-pill")).not.toBeNull()
    expect(container.querySelector("shiny-aside")).toBeNull()
  })

  it("groups a root-level <shiny-aside> tag in html content", () => {
    const { container } = render(
      <MarkdownContent
        content={
          'A claim<shiny-aside label="Source">source body</shiny-aside>.'
        }
        contentType="html"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.querySelector(".shiny-aside-pill")).not.toBeNull()
    expect(container.textContent).toContain("A claim")
  })

  it("attaches a direct html aside to the previous paragraph", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<p>A claim.</p><shiny-aside label="Source">source body</shiny-aside>'
        }
        contentType="html"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    const pill = within(container).getByRole("button", { name: /Source/ })
    expect(pill.closest("p")).toHaveTextContent("A claim.")
    expect(container.querySelectorAll(":scope > p")).toHaveLength(1)
  })

  it("preserves rich html content inside a <shiny-aside> popover", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<p>A claim<shiny-aside label="Source"><p><strong>Details</strong></p><ul><li>one</li></ul></shiny-aside>.</p>'
        }
        contentType="html"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    fireEvent.click(within(container).getByRole("button", { name: /Source/ }))
    const popover = screen.getByRole("dialog")
    expect(within(popover).getByText("Details")).toBeInTheDocument()
    expect(within(popover).getByText("one")).toBeInTheDocument()
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

    const { container } = render(
      <MarkdownContent content={content} contentType="markdown" />,
    )

    expect(container.querySelector("shiny-tool-result")).not.toBeNull()
    expect(container.querySelector(".shiny-tool-card")).toBeNull()
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

  it("does not call parseMarkdown for html content", () => {
    const spy = vi.spyOn(markdownToReactModule, "parseMarkdown")

    render(
      <MarkdownContent
        content={'<div class="custom-html">hello</div>'}
        contentType="html"
      />,
    )

    expect(spy).not.toHaveBeenCalled()

    spy.mockRestore()
  })

  it("renders qualifying suggestion list with card classes", () => {
    const md = [
      "- <span class='suggestion' title='Foo'>do thing</span>",
      "- <span class='suggestion' title='Bar'>other thing</span>",
    ].join("\n")

    const { container } = render(
      <MarkdownContent content={md} contentType="markdown" />,
    )

    expect(
      container.querySelector(".shiny-chat-suggestion-list"),
    ).not.toBeNull()
    const items = container.querySelectorAll(".shiny-chat-suggestion-list-item")
    expect(items.length).toBe(2)
    // Plugin sets data-suggestion to body text, not title
    expect((items[0] as HTMLElement).dataset.suggestion).toBe("do thing")
    expect((items[1] as HTMLElement).dataset.suggestion).toBe("other thing")
  })

  it("streaming round-trip: data-pending present while streaming, cards after, no mutation of cached HAST", () => {
    // A suggestion list that qualifies — it is the last top-level child so the
    // plugin marks it data-pending while streaming=true.
    const md = [
      "- <span class='suggestion' title='Foo'>do thing</span>",
      "- <span class='suggestion' title='Bar'>other thing</span>",
    ].join("\n")

    // 1. Render with streaming=true → list is pending, no cards yet.
    const { container, rerender } = render(
      <MarkdownContent content={md} contentType="markdown" streaming={true} />,
    )

    expect(container.querySelector("[data-pending]")).not.toBeNull()
    expect(
      container.querySelector(".shiny-chat-suggestion-list-item"),
    ).toBeNull()

    // 2. Rerender with streaming=false → cards promoted, no data-pending.
    rerender(
      <MarkdownContent content={md} contentType="markdown" streaming={false} />,
    )

    expect(container.querySelector("[data-pending]")).toBeNull()
    expect(
      container.querySelector(".shiny-chat-suggestion-list-item"),
    ).not.toBeNull()

    // 3. Rerender again with streaming=true → data-pending should be present
    //    again, proving the cached HAST was not mutated by the finalization.
    rerender(
      <MarkdownContent content={md} contentType="markdown" streaming={true} />,
    )

    expect(container.querySelector("[data-pending]")).not.toBeNull()
    expect(
      container.querySelector(".shiny-chat-suggestion-list-item"),
    ).toBeNull()
  })

  it("renders a model-authored raw-HTML island as literal text", () => {
    // Untrusted content is rendered with a component map whose island tags
    // resolve to EscapedIsland (see MarkdownStream's untrusted components) —
    // that map, not the markdown processor, is the spoof guard now that
    // trusted HTML travels as structured html_block envelopes.
    const content =
      '<shiny-chat-raw-html><img data-forged="1" src="x"></shiny-chat-raw-html>'
    const { container } = render(
      <MarkdownContent
        content={content}
        contentType="markdown"
        tagToComponentMap={{ "shiny-chat-raw-html": EscapedIsland }}
      />,
    )

    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("<shiny-chat-raw-html>")
  })
})
