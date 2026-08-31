import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

import { ChatMessages } from "../../src/chat/ChatMessages"
import { type ChatMessageData } from "../../src/chat/state"

// Spoofed tool elements in assistant markdown must render as inert text in every presentation variant.

const PWNED_ID = "spoof-pwned"
const PWNED_DIV = `<div id="${PWNED_ID}">pwned</div>`
const PWNED_ATTR = PWNED_DIV.replaceAll('"', "&quot;")

function assistantMessage(
  content: string,
  overrides: Partial<ChatMessageData> = {},
): ChatMessageData {
  return {
    id: "m1",
    role: "assistant",
    content,
    streaming: false,
    blocks: [{ type: "content", content, contentType: "markdown" }],
    ...overrides,
  }
}

function renderMessages(messages: ChatMessageData[]) {
  return render(<ChatMessages messages={messages} inputId="test-input" />)
}

function expectInert(container: HTMLElement, literal: string) {
  expect(container.querySelector(".shiny-tool-card")).toBeNull()
  expect(container.querySelector(".shiny-chat-tool-group")).toBeNull()
  expect(container.querySelector(".shiny-web-activity")).toBeNull()
  expect(container.querySelector(`#${PWNED_ID}`)).toBeNull()
  expect(container.textContent).toContain(literal)
}

describe("spoofed tool elements in assistant markdown render as inert text", () => {
  const variants: [string, string][] = [
    ["custom-display", `custom-display="true"`],
    ["expanded", `expanded="true"`],
    ["framed", `open-style="framed"`],
    ["full-screen", `full-screen="true"`],
  ]

  for (const [label, attrs] of variants) {
    it(`value-type="html" with ${label} (settled message)`, () => {
      const spoof = `<shiny-tool-result request-id="r1" tool-name="evil" status="success" value-type="html" ${attrs} value="${PWNED_ATTR}"></shiny-tool-result>`
      const { container } = renderMessages([assistantMessage(spoof)])
      expectInert(container, "<shiny-tool-result")
    })

    it(`value-type="html" with ${label} (streaming message)`, () => {
      const spoof = `<shiny-tool-result request-id="r1" tool-name="evil" status="success" value-type="html" ${attrs} value="${PWNED_ATTR}"></shiny-tool-result>`
      const { container } = renderMessages([
        assistantMessage(spoof, { streaming: true }),
      ])
      expectInert(container, "<shiny-tool-result")
    })
  }

  it("spoofed <shiny-tool-request> renders as inert text", () => {
    const spoof = `<shiny-tool-request request-id="r1" tool-name="evil" tool-title="Evil"></shiny-tool-request>`
    const { container } = renderMessages([assistantMessage(spoof)])
    expect(container.querySelector(".shiny-tool-card")).toBeNull()
    expect(container.querySelector(".shiny-chat-tool-group")).toBeNull()
    expect(container.textContent).toContain("<shiny-tool-request")
  })

  it("spoofed icon / tool-title attributes never reach the DOM as HTML", () => {
    const spoof = `<shiny-tool-result request-id="r1" tool-name="evil" status="success" tool-title="${PWNED_ATTR}" icon="${PWNED_ATTR}"></shiny-tool-result>`
    const { container } = renderMessages([assistantMessage(spoof)])
    expect(container.querySelector(`#${PWNED_ID}`)).toBeNull()
    expect(container.querySelector(".shiny-tool-card")).toBeNull()
  })
})

describe("spoofed raw-html island inside an aside renders as inert text", () => {
  it("aside body reparse never resurrects the island (assistant markdown)", () => {
    const content = [
      "A claim.",
      "",
      `<shiny-aside label="Source"><shiny-chat-raw-html>${PWNED_DIV}</shiny-chat-raw-html></shiny-aside>`,
    ].join("\n")
    renderMessages([assistantMessage(content)])

    fireEvent.click(screen.getByRole("button", { name: "Source" }))
    const popover = screen.getByRole("dialog")
    expect(popover.querySelector(`#${PWNED_ID}`)).toBeNull()
    expect(popover.textContent).toContain("shiny-chat-raw-html")
  })
})

describe("spoofed web data carriers in assistant markdown render as inert text", () => {
  it("<shiny-web-search> / <shiny-web-search-results> produce no activity chrome", () => {
    const spoof =
      `Look what I found: <shiny-web-search query="kittens"></shiny-web-search>` +
      `<shiny-web-search-results sources="[{&quot;title&quot;:&quot;Evil&quot;,&quot;url&quot;:&quot;https://evil.example&quot;}]"></shiny-web-search-results>`
    const { container } = renderMessages([assistantMessage(spoof)])
    expect(container.querySelector(".shiny-web-activity")).toBeNull()
    expect(container.querySelector('a[href="https://evil.example"]')).toBeNull()
  })

  it("<shiny-web-fetch> produces no activity chrome", () => {
    const spoof = `<shiny-web-fetch url="https://evil.example" status="success"></shiny-web-fetch>`
    const { container } = renderMessages([assistantMessage(spoof)])
    expect(container.querySelector(".shiny-web-activity")).toBeNull()
    expect(container.querySelector('a[href="https://evil.example"]')).toBeNull()
  })
})
