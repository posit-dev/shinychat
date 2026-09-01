import { describe, it, expect, vi, afterEach } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ToolCard } from "../../src/chat/ToolCard"
import { ChatScrollContext } from "../../src/chat/context"

describe("ToolCard", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("collapsed card body has inert attribute", () => {
    const { container } = render(
      <ToolCard toolName="my_tool" initialExpanded={false}>
        <div>body content</div>
      </ToolCard>,
    )

    const body = container.querySelector(".card-body")
    expect(body).toBeTruthy()
    // inert should be set when collapsed
    expect(body!.hasAttribute("inert")).toBe(true)
  })

  it("expanded card body does not have inert attribute", () => {
    const { container } = render(
      <ToolCard toolName="my_tool" initialExpanded={true}>
        <div>body content</div>
      </ToolCard>,
    )

    const body = container.querySelector(".card-body")
    expect(body).toBeTruthy()
    expect(body!.hasAttribute("inert")).toBe(false)
  })

  it("does not toggle collapse when fullscreen is active", () => {
    const { container } = render(
      <ToolCard toolName="my_tool" initialExpanded={true}>
        <div>body content</div>
      </ToolCard>,
    )

    const card = container.querySelector(".shiny-tool-card")
    const header = container.querySelector(".card-header") as HTMLElement | null
    expect(card).toBeTruthy()
    expect(header).toBeTruthy()

    // Simulate fullscreen state set by useFullscreen
    card!.setAttribute("fullscreen", "")

    // Clicking the header should NOT collapse while fullscreen
    fireEvent.click(header!)
    expect(header!.getAttribute("aria-expanded")).toBe("true")
  })

  it("dispatches a resize event after toggling collapse", () => {
    const { container } = render(
      <ToolCard toolName="my_tool" initialExpanded={false}>
        <div>body content</div>
      </ToolCard>,
    )

    const header = container.querySelector(".card-header") as HTMLElement | null
    expect(header).toBeTruthy()

    const dispatchSpy = vi.spyOn(window, "dispatchEvent")
    const rafSpy = vi
      .spyOn(window, "requestAnimationFrame")
      .mockImplementation((cb: FrameRequestCallback) => {
        cb(0)
        return 1
      })

    fireEvent.click(header!)

    expect(header!.getAttribute("aria-expanded")).toBe("true")
    expect(rafSpy).toHaveBeenCalled()
    expect(dispatchSpy).toHaveBeenCalledWith(expect.any(Event))
    expect(
      dispatchSpy.mock.calls.some(
        ([event]) => event instanceof Event && event.type === "resize",
      ),
    ).toBe(true)
  })

  it("disengages the outer chat's stick-to-bottom before expanding, so opening a card doesn't yank the scroll position away", () => {
    // The outer chat message list auto-scrolls to the bottom on any resize
    // while it's pinned there. Toggling a tool card resizes the message list
    // too, so without disengaging first, expanding an older card would drag
    // the viewport down past the very thing the user just clicked to see.
    const stopScroll = vi.fn()
    const { container } = render(
      <ChatScrollContext.Provider value={stopScroll}>
        <ToolCard toolName="my_tool" initialExpanded={false}>
          <div>body content</div>
        </ToolCard>
      </ChatScrollContext.Provider>,
    )
    const header = container.querySelector(".card-header") as HTMLElement
    fireEvent.click(header)
    expect(stopScroll).toHaveBeenCalled()
  })

  it("disengages the outer chat's stick-to-bottom before collapsing too", () => {
    const stopScroll = vi.fn()
    const { container } = render(
      <ChatScrollContext.Provider value={stopScroll}>
        <ToolCard toolName="my_tool" initialExpanded={true}>
          <div>body content</div>
        </ToolCard>
      </ChatScrollContext.Provider>,
    )
    const header = container.querySelector(".card-header") as HTMLElement
    fireEvent.click(header)
    expect(stopScroll).toHaveBeenCalled()
  })

  it("renders toolTitle as HTML (developer-controlled content)", () => {
    const { container } = render(
      <ToolCard toolName="safe" toolTitle="<b>bold</b>">
        <div>body</div>
      </ToolCard>,
    )

    const nameSpan = container.querySelector(".tool-title-name")
    expect(nameSpan).toBeTruthy()
    expect(nameSpan!.querySelector("b")).toBeTruthy()
    expect(nameSpan!.textContent).toBe("bold")
  })

  it("escapes the toolName fallback when no toolTitle is provided (model-influenced text)", () => {
    const payload = "<img src=x onerror=alert(1)>"
    const { container } = render(
      <ToolCard toolName={payload} initialExpanded={true}>
        <div>body</div>
      </ToolCard>,
    )

    const nameSpan = container.querySelector(".tool-title-name")
    expect(nameSpan).toBeTruthy()
    expect(nameSpan!.querySelector("img")).toBeNull()
    expect(nameSpan!.textContent).toContain(payload)
  })

  it("does not wrap the title in a 'Running '/'failed' template (titleTemplate removed)", () => {
    const { container } = render(
      <ToolCard toolName="search" toolTitle="Searching" statusNote="failed">
        <div>body</div>
      </ToolCard>,
    )

    // The title is rendered verbatim, with no prefix/suffix wrapper baked in.
    expect(container.querySelector(".tool-title-name")?.textContent).toBe(
      "Searching",
    )
    expect(container.querySelector(".tool-title")?.textContent).not.toContain(
      "Running ",
    )
    // "failed" appears only in the separate status-note element, not appended
    // to the title text itself.
    expect(container.querySelector(".tool-title")?.textContent).not.toContain(
      "failed",
    )
    expect(container.querySelector(".tool-status-note")?.textContent).toBe(
      "failed",
    )
  })
})

describe("ToolCard error containment", () => {
  function ThrowingBody(): never {
    throw new Error("bad tool metadata")
  }

  it("a throwing card body leaves the header intact", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { container, getByRole } = render(
      <ToolCard toolName="my_tool" initialExpanded={true}>
        <ThrowingBody />
      </ToolCard>,
    )

    // The header row still renders and remains expandable.
    const header = container.querySelector(".card-header")
    expect(header).toBeTruthy()
    expect(header!.textContent).toContain("my_tool")
    // The body degrades to an inline notice.
    expect(getByRole("alert").textContent).toContain("couldn’t be displayed")
  })

  it("a throwing footer leaves the card intact", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const { container, queryByRole, getByText } = render(
      <ToolCard
        toolName="my_tool"
        initialExpanded={true}
        footer={
          {
            toString: () => {
              throw new Error("bad footer")
            },
          } as unknown as string
        }
      >
        <div>body content</div>
      </ToolCard>,
    )

    // Footer is dropped (fallback null), body and header survive.
    expect(getByText("body content")).toBeTruthy()
    expect(container.querySelector(".card-header")).toBeTruthy()
    expect(queryByRole("alert")).toBeNull()
  })

  it("recovers when a throwing footer is corrected", () => {
    vi.spyOn(console, "warn").mockImplementation(() => {})
    vi.spyOn(console, "error").mockImplementation(() => {})

    const badFooter = {
      toString: () => {
        throw new Error("bad footer")
      },
    } as unknown as string
    const { rerender, container, queryByRole } = render(
      <ToolCard toolName="my_tool" initialExpanded={true} footer={badFooter}>
        <div>body content</div>
      </ToolCard>,
    )
    expect(container.querySelector(".card-footer")).toBeNull()

    rerender(
      <ToolCard toolName="my_tool" initialExpanded={true} footer="<p>fixed</p>">
        <div>body content</div>
      </ToolCard>,
    )
    expect(queryByRole("alert")).toBeNull()
    expect(container.querySelector(".card-footer")).toBeTruthy()
    expect(container.querySelector(".card-footer")!.innerHTML).toContain(
      "fixed",
    )
  })
})
