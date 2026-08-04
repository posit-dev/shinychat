import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { MarkdownContent } from "../../src/markdown/MarkdownContent"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"

// Assistant markdown is model output. It must never reach a raw-HTML sink.
// The server only emits shinychat's raw-HTML elements as content_type "html",
// so their appearance in markdown means something is trying to break out.

describe("reserved elements in markdown content are inert", () => {
  it("does not write an event-handler payload to innerHTML via a raw-html island", () => {
    const { container } = render(
      <MarkdownContent
        content={
          "<shinychat-raw-html><img src=x onerror=alert(1)></shinychat-raw-html>"
        }
        contentType="markdown"
      />,
    )

    // React still renders the inner <img>, but inertly: no event handler
    // survives, and the island name shows up as text rather than as a wrapper.
    expect(container.querySelector("[onerror]")).toBeNull()
    expect(container.innerHTML).not.toContain("onerror")
    expect(container.textContent).toContain("shinychat-raw-html")
  })

  it("escapes the island regardless of tag case", () => {
    const { container } = render(
      <MarkdownContent
        content={
          "<SHINYCHAT-RAW-HTML><img src=x onerror=alert(1)></SHINYCHAT-RAW-HTML>"
        }
        contentType="markdown"
      />,
    )

    expect(container.querySelector("[onerror]")).toBeNull()
    expect(container.innerHTML).not.toContain("onerror")
    expect(container.textContent?.toLowerCase()).toContain("shinychat-raw-html")
  })

  it("does not render a tool card, so its icon attribute never reaches dangerouslySetInnerHTML", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<shiny-tool-result request-id="1" tool-name="x" status="success" value="v" value-type="text" icon="<img src=y onerror=alert(2)>"></shiny-tool-result>'
        }
        contentType="markdown"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.querySelector(".shiny-tool-card")).toBeNull()
    expect(container.innerHTML).not.toContain("onerror")
  })

  it("does not render a tool request card from markdown", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<shiny-tool-request data-shinychat-react request-id="1" tool-name="t" arguments="{}"></shiny-tool-request>'
        }
        contentType="markdown"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.querySelector(".shiny-tool-card")).toBeNull()
  })

  it("does not smuggle a payload through a tool-name attribute", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<shiny-tool-result request-id="1" tool-name="<img src=z onerror=alert(3)>" status="success" value="v" value-type="text"></shiny-tool-result>'
        }
        contentType="markdown"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.innerHTML).not.toContain("onerror")
  })

  it("leaves ordinary raw HTML in markdown rendering as before (React makes it inert)", () => {
    const { container } = render(
      <MarkdownContent
        content={'<div class="custom">hi</div>'}
        contentType="markdown"
      />,
    )

    expect(container.querySelector(".custom")).not.toBeNull()
    expect(container.textContent).toContain("hi")
  })
})

describe("reserved elements in html content still render", () => {
  it("renders a raw-html island from server-sent html content", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<shinychat-raw-html><div class="widget">Hello</div></shinychat-raw-html>'
        }
        contentType="html"
      />,
    )

    expect(container.querySelector(".widget")).not.toBeNull()
  })

  it("renders a tool card from server-sent html content", () => {
    const { container } = render(
      <MarkdownContent
        content={
          '<shiny-tool-request data-shinychat-react request-id="req-1" tool-name="test" arguments="{}"></shiny-tool-request>'
        }
        contentType="html"
        tagToComponentMap={chatTagToComponentMap}
      />,
    )

    expect(container.querySelector(".shiny-tool-card")).not.toBeNull()
  })
})
