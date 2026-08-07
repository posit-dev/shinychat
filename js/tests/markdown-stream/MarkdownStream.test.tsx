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
})
