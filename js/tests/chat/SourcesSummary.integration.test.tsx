import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup, fireEvent } from "@testing-library/react"
import { markdownProcessor } from "../../src/markdown/processors"
import { parseMarkdown, hastToReact } from "../../src/markdown/markdownToReact"
import { chatTagToComponentMap } from "../../src/chat/chatTagToComponentMap"
import { CitationCollectorProvider } from "../../src/chat/citationCollector"
import { SourcesSummary } from "../../src/chat/SourcesSummary"
import { AsideGroupView } from "../../src/chat/AsideGroup"

afterEach(cleanup)

// Mirrors the server's citation markup emitted by citation_aside(url, title).
function cite(url: string, title: string): string {
  return `<shiny-aside data-citation label="${new URL(url).hostname}" url="${url}"><a href="${url}">${title}</a></shiny-aside>`
}

function messageEl(md: string) {
  const hast = parseMarkdown(md, markdownProcessor)
  return (
    <CitationCollectorProvider>
      {hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })}
      <SourcesSummary />
    </CitationCollectorProvider>
  )
}

function renderMessage(md: string) {
  return render(messageEl(md))
}

describe("SourcesSummary wiring", () => {
  it("registers normalized citation entries without serialized markup", () => {
    render(
      <CitationCollectorProvider>
        <AsideGroupView
          entries={[
            {
              label: "example.com",
              url: "https://example.com/source",
              body: "Evidence",
              citation: { title: "Example source" },
            },
          ]}
        />
        <SourcesSummary />
      </CitationCollectorProvider>,
    )

    expect(
      screen.getByRole("button", { name: "Sources, 1 source" }),
    ).toBeInTheDocument()
  })

  it("aggregates and dedups citations across the whole message", () => {
    renderMessage(
      [
        `Hub motors are cheaper${cite("https://ebicycles.example/hub", "Hub vs Mid-Drive")}`,
        ` and ideal for flat terrain${cite("https://wired.example/motors", "How Motors Work")}.`,
        "",
        `A generic note<shiny-aside>Not a citation.</shiny-aside>.`,
        "",
        `Range depends on battery${cite("https://ebicycles.example/hub", "Hub vs Mid-Drive")}.`,
      ].join("\n"),
    )
    // Two distinct citation URLs across the message (ebicycles cited twice, wired once);
    // the hand-authored aside is excluded.
    const pill = screen.getByRole("button", { name: /Sources, 2 sources/ })
    expect(pill).toBeInTheDocument()
    fireEvent.click(pill)
    const dialog = screen.getByRole("dialog")
    expect(dialog).toHaveTextContent("ebicycles.example")
    expect(dialog).toHaveTextContent("wired.example")
    expect(dialog).not.toHaveTextContent("Not a citation")
  })

  it("keeps a source registered when the same url is cited by a separate group that unmounts", () => {
    // Two independently-keyed paragraphs (each its own <shiny-aside-group>,
    // as rehypeGroupAsides produces) citing the SAME url. Keying the wrapper
    // divs lets React truly unmount the first one on rerender instead of
    // reconciling it in place — the scenario a content-derived registration
    // key (rather than a stable per-instance id) would get wrong: the first
    // group's unmount cleanup would delete the shared registry slot that the
    // still-mounted second group also depends on.
    const url = "https://ebicycles.example/hub"
    const groupEl = (text: string) => {
      const hast = parseMarkdown(
        `${text}${cite(url, "Hub vs Mid-Drive")}.`,
        markdownProcessor,
      )
      return hastToReact(hast, { tagToComponentMap: chatTagToComponentMap })
    }
    const twoGroupsEl = (showFirst: boolean) => (
      <CitationCollectorProvider>
        {showFirst && <div key="first">{groupEl("A")}</div>}
        <div key="second">{groupEl("B")}</div>
        <SourcesSummary />
      </CitationCollectorProvider>
    )

    const { rerender } = render(twoGroupsEl(true))
    expect(
      screen.getByRole("button", { name: /Sources, 1 source\b/ }),
    ).toBeInTheDocument()

    rerender(twoGroupsEl(false))

    expect(
      screen.getByRole("button", { name: /Sources, 1 source\b/ }),
    ).toBeInTheDocument()
  })
})
