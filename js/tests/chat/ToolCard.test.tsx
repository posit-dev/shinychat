import { describe, it, expect, vi, afterEach } from "vitest"
import { render, fireEvent } from "@testing-library/react"
import { ToolCard } from "../../src/chat/ToolCard"

describe("ToolCard", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("collapsed card body has inert attribute", () => {
    const { container } = render(
      <ToolCard requestId="test-1" toolName="my_tool" initialExpanded={false}>
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
      <ToolCard requestId="test-2" toolName="my_tool" initialExpanded={true}>
        <div>body content</div>
      </ToolCard>,
    )

    const body = container.querySelector(".card-body")
    expect(body).toBeTruthy()
    expect(body!.hasAttribute("inert")).toBe(false)
  })

  it("does not toggle collapse when fullscreen is active", () => {
    const { container } = render(
      <ToolCard requestId="test-3" toolName="my_tool" initialExpanded={true}>
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
      <ToolCard requestId="test-4" toolName="my_tool" initialExpanded={false}>
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

  it("renders toolTitle as HTML (developer-controlled content)", () => {
    const { container } = render(
      <ToolCard requestId="xss-2" toolName="safe" toolTitle="<b>bold</b>">
        <div>body</div>
      </ToolCard>,
    )

    const nameSpan = container.querySelector(".tool-title-name")
    expect(nameSpan).toBeTruthy()
    expect(nameSpan!.querySelector("b")).toBeTruthy()
    expect(nameSpan!.textContent).toBe("bold")
  })

  it("does not wrap the title in a 'Running '/'failed' template (titleTemplate removed)", () => {
    const { container } = render(
      <ToolCard
        requestId="no-template"
        toolName="search"
        toolTitle="Searching"
        statusNote="failed"
      >
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
