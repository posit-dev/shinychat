import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup, fireEvent } from "@testing-library/react"
import { markdownProcessor } from "../../src/markdown/processors"
import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"

afterEach(cleanup)

function renderMarkdown(md: string) {
  const hast = parseMarkdown(md, markdownProcessor)
  return render(
    <>{hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })}</>,
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
