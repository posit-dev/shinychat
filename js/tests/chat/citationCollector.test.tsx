import { describe, it, expect, afterEach } from "vitest"
import { render, screen, cleanup } from "@testing-library/react"
import { useEffect } from "react"
import {
  CitationCollectorProvider,
  useCitationRegister,
  useCitations,
} from "../../src/chat/citationCollector"
import type { CitationEntry } from "../../src/chat/citations"

afterEach(cleanup)

function Producer({ id, entries }: { id: string; entries: CitationEntry[] }) {
  const registry = useCitationRegister()
  useEffect(() => {
    if (!registry) return
    registry.register(id, entries)
    return () => registry.unregister(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])
  return null
}

function Readout() {
  const citations = useCitations()
  return <div data-testid="urls">{citations.map((c) => c.url).join(",")}</div>
}

function RegisterReadout() {
  const registry = useCitationRegister()
  return (
    <div data-testid="registry">{registry === null ? "null" : "present"}</div>
  )
}

describe("CitationCollectorProvider", () => {
  it("useCitationRegister returns null outside a provider", () => {
    render(<RegisterReadout />)
    expect(screen.getByTestId("registry")).toHaveTextContent("null")
  })

  it("aggregates and dedups entries registered by producers", () => {
    render(
      <CitationCollectorProvider>
        <Producer
          id="p1"
          entries={[{ url: "https://a.example", domain: "a.example" }]}
        />
        <Producer
          id="p2"
          entries={[
            { url: "https://b.example", domain: "b.example" },
            { url: "https://a.example", domain: "a.example" },
          ]}
        />
        <Readout />
      </CitationCollectorProvider>,
    )
    expect(screen.getByTestId("urls")).toHaveTextContent(
      "https://a.example,https://b.example",
    )
  })
})
