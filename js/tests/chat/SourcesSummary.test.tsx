import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup, fireEvent } from "@testing-library/react"
import { SourcesSummaryView } from "../../src/chat/SourcesSummary"
import { AsideFaviconContext } from "../../src/chat/context"

afterEach(cleanup)

const sources = [
  {
    url: "https://ebicycles.example/x",
    domain: "ebicycles.example",
    title: "Hub vs Mid-Drive",
  },
  {
    url: "https://wired.example/y",
    domain: "wired.example",
    title: "How Motors Work",
  },
]

describe("SourcesSummaryView", () => {
  it("renders nothing when there are no sources", () => {
    const { container } = render(<SourcesSummaryView sources={[]} />)
    expect(container.querySelector(".shiny-sources-pill")).toBeNull()
  })

  it("renders a Sources pill whose accessible name includes the count", () => {
    render(<SourcesSummaryView sources={sources} />)
    expect(
      screen.getByRole("button", { name: /Sources, 2 sources/ }),
    ).toBeInTheDocument()
  })

  it("lists each deduped source with its domain, title, and link on open", () => {
    render(<SourcesSummaryView sources={sources} />)
    fireEvent.click(screen.getByRole("button", { name: /Sources/ }))
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent("ebicycles.example")
    expect(dialog).toHaveTextContent("Hub vs Mid-Drive")
    const link = screen.getByRole("link", { name: /How Motors Work/ })
    expect(link).toHaveAttribute("href", "https://wired.example/y")
    expect(link).toHaveAttribute("data-shinychat-link", "")
  })

  it("falls back to the domain as the title when a source has none", () => {
    render(
      <SourcesSummaryView
        sources={[{ url: "https://x.example/p", domain: "x.example" }]}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /Sources/ }))
    const title = document.querySelector(".shiny-sources-item__title")
    expect(title).toHaveTextContent("x.example")
  })

  it("falls back to the url as the title when a source has neither title nor domain", () => {
    render(<SourcesSummaryView sources={[{ url: "https://x.example/p" }]} />)
    fireEvent.click(screen.getByRole("button", { name: /Sources/ }))
    const title = document.querySelector(".shiny-sources-item__title")
    expect(title).toHaveTextContent("https://x.example/p")
  })

  it("caps the collapsed pill's favicon stack at MAX_STACK even with more sources", () => {
    const manySources = Array.from({ length: 5 }, (_, i) => ({
      url: `https://example${i}.example/p`,
      domain: `example${i}.example`,
      title: `Title ${i}`,
    }))
    const { container } = render(<SourcesSummaryView sources={manySources} />)
    const stack = container.querySelector(".shiny-sources-pill__stack")
    expect(stack?.children.length).toBeLessThanOrEqual(3)
  })

  it("does not load derived favicons when the deployment disables them", () => {
    const { container } = render(
      <AsideFaviconContext.Provider value={false}>
        <SourcesSummaryView sources={sources} />
      </AsideFaviconContext.Provider>,
    )

    expect(container.querySelector(".shiny-sources-pill img")).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: /Sources/ }))

    expect(document.querySelector(".shiny-sources-popover img")).toBeNull()
  })

  it("preserves a scoped Bootstrap theme in its portaled popover", () => {
    render(
      <div data-bs-theme="dark">
        <SourcesSummaryView sources={sources} />
      </div>,
    )

    fireEvent.click(screen.getByRole("button", { name: /Sources/ }))

    expect(document.querySelector(".shiny-sources-popover")).toHaveAttribute(
      "data-bs-theme",
      "dark",
    )
  })
})
