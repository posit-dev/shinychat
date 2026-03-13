import { describe, it, expect } from "vitest"
import { render } from "@testing-library/react"
import { ToolCard } from "../../src/chat/ToolCard"

describe("ToolCard", () => {
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
    header!.click()
    expect(header!.getAttribute("aria-expanded")).toBe("true")
  })
})
