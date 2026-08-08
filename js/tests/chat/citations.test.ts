import { describe, it, expect } from "vitest"
import {
  mergeCitations,
  citationEntriesFromAsides,
} from "../../src/chat/citations"

describe("mergeCitations", () => {
  it("dedups by url, keeps first-seen order", () => {
    const out = mergeCitations([
      { url: "https://a.example", domain: "a.example", title: "A" },
      { url: "https://b.example", domain: "b.example", title: "B" },
      { url: "https://a.example", domain: "a.example", title: "A again" },
    ])
    expect(out.map((e) => e.url)).toEqual([
      "https://a.example",
      "https://b.example",
    ])
  })

  it("keeps the first non-empty title when a later duplicate has one and the first did not", () => {
    const out = mergeCitations([
      { url: "https://a.example", domain: "a.example", title: undefined },
      { url: "https://a.example", domain: "a.example", title: "Real Title" },
    ])
    expect(out).toHaveLength(1)
    expect(out[0]!.title).toBe("Real Title")
  })
})

describe("citationEntriesFromAsides", () => {
  it("projects only normalized citation entries for the Sources summary", () => {
    const out = citationEntriesFromAsides([
      {
        label: "a.example",
        url: "https://a.example",
        body: '<a href="https://a.example">Title A</a>',
        citation: {
          title: "Title A",
          cited_quote: "Source evidence",
        },
        groundingId: "aside-grounding-1",
      },
      { body: "hand-authored aside" },
    ])
    expect(out).toEqual([
      { url: "https://a.example", domain: "a.example", title: "Title A" },
    ])
  })

  it("ignores citation entries without a source URL", () => {
    expect(
      citationEntriesFromAsides([
        { label: "Missing URL", citation: { title: "Title" } },
      ]),
    ).toEqual([])
  })
})
