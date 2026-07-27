import { describe, it, expect } from "vitest"
import type { Element } from "hast"
import {
  mergeCitations,
  citationEntriesFromGroup,
} from "../../src/chat/citations"

function citationAside(
  url: string,
  label: string,
  anchorText: string,
): Element {
  return {
    type: "element",
    tagName: "shiny-aside",
    properties: { dataCitation: "", label, url },
    children: [
      {
        type: "element",
        tagName: "a",
        properties: { href: url },
        children: [{ type: "text", value: anchorText }],
      },
    ],
  }
}

function plainAside(text: string): Element {
  return {
    type: "element",
    tagName: "shiny-aside",
    properties: {},
    children: [{ type: "text", value: text }],
  }
}

function group(...children: Element[]): Element {
  return {
    type: "element",
    tagName: "shiny-aside-group",
    properties: {},
    children,
  }
}

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

describe("citationEntriesFromGroup", () => {
  it("extracts only citation asides, with url/domain/title", () => {
    const out = citationEntriesFromGroup(
      group(
        citationAside("https://a.example", "a.example", "Title A"),
        plainAside("hand-authored aside"),
      ),
    )
    expect(out).toEqual([
      { url: "https://a.example", domain: "a.example", title: "Title A" },
    ])
  })

  it("treats anchor text equal to the url as no title (falls back later)", () => {
    const out = citationEntriesFromGroup(
      group(
        citationAside("https://a.example", "a.example", "https://a.example"),
      ),
    )
    expect(out[0]!.title).toBeUndefined()
  })
})
