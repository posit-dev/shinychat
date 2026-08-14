import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup, fireEvent } from "@testing-library/react"
import { markdownProcessor } from "../../src/markdown/processors"
import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"
import { AsideFaviconContext } from "../../src/chat/context"

afterEach(cleanup)

function renderMarkdown(md: string, deriveFavicon = true) {
  const hast = parseMarkdown(md, markdownProcessor)
  return render(
    <AsideFaviconContext.Provider value={deriveFavicon}>
      {hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })}
    </AsideFaviconContext.Provider>,
  )
}

const SOURCES = JSON.stringify([
  {
    url: "https://accio.com/x",
    title: "2025 Electric Bike Trends",
    domain: "accio.com",
  },
  {
    url: "https://wired.com/y",
    title: "Why e-bikes boom",
    domain: "wired.com",
  },
])

const MD = [
  '<shiny-web-search query="e-bike trends 2025"></shiny-web-search>',
  "",
  `<shiny-web-search-results sources='${SOURCES}'></shiny-web-search-results>`,
  "",
  '<shiny-web-fetch url="https://en.wikipedia.org/wiki/Electric_bicycle" status="success"></shiny-web-fetch>',
].join("\n")

describe("WebActivity", () => {
  it("renders one collapsible header, collapsed by default", () => {
    renderMarkdown(MD)
    expect(screen.getByText("Searched the web")).toBeInTheDocument()
    expect(
      screen.queryByText("2025 Electric Bike Trends"),
    ).not.toBeInTheDocument()
  })

  it("expands to show query, result count, rows, and the fetch node", () => {
    renderMarkdown(MD)
    fireEvent.click(screen.getByText("Searched the web"))
    expect(screen.getByText("e-bike trends 2025")).toBeInTheDocument()
    expect(screen.getByText("2 results")).toBeInTheDocument()
    expect(screen.getByText("2025 Electric Bike Trends")).toBeInTheDocument()
    expect(screen.getByText("accio.com")).toBeInTheDocument()
    expect(
      screen.getByText("https://en.wikipedia.org/wiki/Electric_bicycle"),
    ).toBeInTheDocument()
  })

  it("marks result and fetch links for external-link confirmation", () => {
    renderMarkdown(MD)
    fireEvent.click(screen.getByText("Searched the web"))

    const resultLink = screen
      .getByText("2025 Electric Bike Trends")
      .closest("a")
    const fetchLink = screen
      .getByText("https://en.wikipedia.org/wiki/Electric_bicycle")
      .closest("a")

    expect(resultLink).toHaveAttribute("data-shinychat-link", "")
    expect(fetchLink).toHaveAttribute("data-shinychat-link", "")
  })

  it("keeps batched result lists with their corresponding queries", () => {
    const rSources = JSON.stringify([
      {
        url: "https://cran.r-project.org/bin/windows/base/old/4.5.0/",
        title: "Previous releases of R for Windows",
        domain: "cran.r-project.org",
      },
    ])
    const pythonSources = JSON.stringify([
      {
        url: "https://www.python.org/downloads/release/python-3140/",
        title: "Python Release Python 3.14.0",
        domain: "www.python.org",
      },
    ])
    const md = [
      '<shiny-web-search query="R 4.5.0 release date"></shiny-web-search>',
      '<shiny-web-search query="Python 3.14.0 release date"></shiny-web-search>',
      `<shiny-web-search-results sources='${rSources}'></shiny-web-search-results>`,
      `<shiny-web-search-results sources='${pythonSources}'></shiny-web-search-results>`,
    ].join("\n")

    const { container } = renderMarkdown(md)
    fireEvent.click(screen.getByText("Searched the web"))

    const searches = container.querySelectorAll(".shiny-web-activity__search")
    expect(searches).toHaveLength(2)
    expect(searches[0]).toHaveTextContent("R 4.5.0 release date")
    expect(searches[0]).toHaveTextContent("Previous releases of R for Windows")
    expect(searches[0]).not.toHaveTextContent("Python Release Python 3.14.0")
    expect(searches[1]).toHaveTextContent("Python 3.14.0 release date")
    expect(searches[1]).toHaveTextContent("Python Release Python 3.14.0")
    expect(searches[1]).not.toHaveTextContent(
      "Previous releases of R for Windows",
    )
  })

  it("does not imply zero results when only search activity was provided", () => {
    renderMarkdown(
      '<shiny-web-search query="Python current release"></shiny-web-search>',
    )
    fireEvent.click(screen.getByText("Searched the web"))

    expect(screen.getByText("Python current release")).toBeInTheDocument()
    expect(screen.queryByText("0 results")).not.toBeInTheDocument()
  })

  it("does not render a count for an empty result list", () => {
    renderMarkdown(
      [
        '<shiny-web-search query="Python current release"></shiny-web-search>',
        "",
        '<shiny-web-search-results sources="[]"></shiny-web-search-results>',
      ].join("\n"),
    )
    fireEvent.click(screen.getByText("Searched the web"))

    expect(screen.getByText("Python current release")).toBeInTheDocument()
    expect(screen.queryByText("0 results")).not.toBeInTheDocument()
  })

  it("shows answer citations as sources when search results are unavailable", () => {
    renderMarkdown(
      [
        '<shiny-web-search query="Python current release"></shiny-web-search>',
        "",
        "Python 3.14.7 is current.",
        '<shiny-aside data-citation url="https://www.python.org/downloads/"><a href="https://www.python.org/downloads/">Download Python | Python.org</a></shiny-aside>',
      ].join("\n"),
    )
    fireEvent.click(screen.getByText("Searched the web"))

    expect(screen.getByText("Cited sources")).toBeInTheDocument()
    const sourceLink = screen
      .getByText("Download Python | Python.org")
      .closest("a")
    expect(sourceLink).toHaveAttribute(
      "href",
      "https://www.python.org/downloads/",
    )
    expect(
      screen.getAllByText("www.python.org", {
        selector: ".shiny-web-activity__domain",
      }),
    ).toHaveLength(1)
  })

  it("shows answer citations once for multiple searches without results", () => {
    renderMarkdown(
      [
        '<shiny-web-search query="Python current release"></shiny-web-search>',
        '<shiny-web-search query="Python supported versions"></shiny-web-search>',
        "",
        "Python 3.14.7 is current.",
        '<shiny-aside data-citation url="https://www.python.org/downloads/"><a href="https://www.python.org/downloads/">Download Python | Python.org</a></shiny-aside>',
      ].join("\n"),
    )
    fireEvent.click(screen.getByText("Searched the web"))

    expect(screen.getAllByText("Cited sources")).toHaveLength(1)
    expect(
      screen.getAllByText("www.python.org", {
        selector: ".shiny-web-activity__domain",
      }),
    ).toHaveLength(1)
  })

  it("falls back to the domain when a source has no title", () => {
    const md = [
      '<shiny-web-search query="q"></shiny-web-search>',
      "",
      `<shiny-web-search-results sources='${JSON.stringify([{ url: "https://only-domain.com/p", domain: "only-domain.com" }])}'></shiny-web-search-results>`,
    ].join("\n")
    renderMarkdown(md)
    fireEvent.click(screen.getByText("Searched the web"))
    expect(
      screen.getAllByText("only-domain.com").length,
    ).toBeGreaterThanOrEqual(1)
  })

  it("does not load derived favicons when the deployment disables them", () => {
    const { container } = renderMarkdown(MD, false)

    fireEvent.click(screen.getByText("Searched the web"))

    expect(
      container.querySelector(".shiny-web-activity__results img"),
    ).toBeNull()
  })

  it("shows an error status for a failed fetch", () => {
    const md = '<shiny-web-fetch url="failed" status="error"></shiny-web-fetch>'
    const { container } = renderMarkdown(md)
    // A fetch-only burst is labeled "Read the web", not "Searched the web"
    fireEvent.click(screen.getByText("Read the web"))
    expect(screen.getByText("failed")).not.toHaveAttribute("href")
    expect(screen.getByText("✗")).toBeInTheDocument()
    expect(
      container.querySelector(".shiny-web-activity__status--error"),
    ).not.toBeNull()
  })
})
