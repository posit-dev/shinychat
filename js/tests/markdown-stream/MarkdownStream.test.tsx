import { render, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import { ShinyLifecycleContext } from "../../src/chat/context"

const containerRef = vi.fn()
const scrollToBottom = vi.fn()
const engageStickToBottom = vi.fn()
const repinIfAtBottom = vi.fn()
const findScrollableParent = vi.fn()

vi.mock("../../src/markdown/useAutoScroll", () => ({
  useAutoScroll: vi.fn(() => ({
    containerRef,
    stickToBottom: true,
    scrollToBottom,
    engageStickToBottom,
    repinIfAtBottom,
  })),
  findScrollableParent: (...args: Parameters<typeof findScrollableParent>) =>
    findScrollableParent(...args),
}))

import {
  MarkdownStream,
  type MarkdownStreamApi,
} from "../../src/markdown-stream/MarkdownStream"

describe("MarkdownStream", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("re-scans for a scroll parent as content grows", () => {
    let api: MarkdownStreamApi | undefined
    const scrollParent = document.createElement("div")

    findScrollableParent.mockReturnValueOnce(null)

    render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          autoScroll={true}
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    expect(findScrollableParent).toHaveBeenCalled()
    expect(containerRef).not.toHaveBeenCalledWith(scrollParent)

    findScrollableParent.mockReturnValue(scrollParent)

    act(() => {
      api?.appendContent("streamed content")
    })

    expect(containerRef).toHaveBeenCalledWith(scrollParent)
  })

  it("settles pinnedness before an appended chunk reaches the DOM", () => {
    // posit-dev/py-shiny#2378: pinnedness has to be decided while the DOM still
    // holds the pre-growth scrollHeight, otherwise the grown content makes the
    // user's at-bottom position read as "scrolled away".
    let api: MarkdownStreamApi | undefined
    let domAtRepinTime: string | undefined

    repinIfAtBottom.mockImplementation(() => {
      domAtRepinTime = container.textContent ?? ""
    })

    const { container } = render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream
          autoScroll={true}
          onApiReady={(value) => {
            api = value
          }}
        />
      </ShinyLifecycleContext.Provider>,
    )

    act(() => {
      api?.appendContent("streamed chunk")
    })

    expect(repinIfAtBottom).toHaveBeenCalledTimes(1)
    expect(domAtRepinTime).not.toContain("streamed chunk")
    expect(container.textContent).toContain("streamed chunk")
  })

  it("stops scroll-parent discovery at the chat container boundary", () => {
    render(
      <ShinyLifecycleContext.Provider
        value={{
          bindAll: vi.fn(async () => {}),
          unbindAll: vi.fn(),
          renderDependencies: vi.fn(async () => {}),
          showClientMessage: vi.fn(),
        }}
      >
        <MarkdownStream autoScroll={true} />
      </ShinyLifecycleContext.Provider>,
    )

    expect(findScrollableParent).toHaveBeenCalledWith(
      expect.any(HTMLDivElement),
      "shiny-chat-container",
    )
  })

  it("keeps an island split across untrusted chunks inert", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("## Heading\n\n<shiny-chat-")
      api?.appendContent(
        'raw-html><img data-forged="1" src="x"></shiny-chat-raw-html>',
      )
    })

    expect(container.querySelector("h2")).not.toBeNull()
    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("<shiny-chat-raw-html>")
  })

  it("renders adjacent markdown and trusted HTML segments", () => {
    const { container } = render(
      <MarkdownStream
        initialSegments={[
          { text: "## This is markdown", trusted: false },
          {
            text: "<shiny-chat-raw-html><div data-html>HTML</div></shiny-chat-raw-html>",
            trusted: true,
          },
        ]}
      />,
    )

    expect(container.querySelector("h2")?.textContent).toBe("This is markdown")
    expect(container.querySelector("[data-html]")?.textContent).toBe("HTML")
  })

  it("does not let untrusted content merge into a trusted run", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent(
        "<shiny-chat-raw-html><div data-trusted>safe</div></shiny-chat-raw-html>",
        true,
      )
      api?.appendContent(
        "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
        false,
      )
    })

    expect(container.querySelector("[data-trusted]")).not.toBeNull()
    expect(container.querySelector("[data-forged]")).toBeNull()
  })

  it("preserves an explicit markdown segment boundary at equal trust", () => {
    let api: MarkdownStreamApi | undefined
    const { container } = render(
      <MarkdownStream
        onApiReady={(value) => {
          api = value
        }}
      />,
    )

    act(() => {
      api?.appendContent("preceding model output")
      api?.appendContent("## Composite heading", false, true)
    })

    expect(container.querySelector("h2")?.textContent).toBe("Composite heading")
  })

  it("fails closed for untrusted html-typed islands", () => {
    const { container } = render(
      <MarkdownStream
        initialContentType="html"
        initialSegments={[
          {
            text: "<shiny-chat-raw-html><div data-forged>unsafe</div></shiny-chat-raw-html>",
            trusted: false,
          },
        ]}
      />,
    )

    expect(container.querySelector("[data-forged]")).toBeNull()
    expect(container.textContent).toContain("shiny-chat-raw-html")
  })
})
