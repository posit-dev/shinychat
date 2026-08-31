import { describe, it, expect } from "vitest"
import {
  appendWebActivityBlock,
  isWhitespaceContentBlock,
  type WebActivityBlock,
} from "../../src/chat/web-activity-model"
import type { ContentBlock, MessageBlock } from "../../src/chat/state"
import type {
  WebFetchBlock,
  WebSearchBlock,
  WebSearchResultsBlock,
} from "../../src/transport/types"

const webSearchBlock = (): WebSearchBlock => ({
  type: "web_search",
  version: 1,
  query: "weather in Duluth",
})

const webSearchResultsBlock = (): WebSearchResultsBlock => ({
  type: "web_search_results",
  version: 1,
  sources: [
    { url: "https://example.com/weather", title: "Duluth weather" },
    { url: "https://example.org/forecast" },
  ],
})

const webFetchBlock = (): WebFetchBlock => ({
  type: "web_fetch",
  version: 1,
  url: "https://example.net/article",
  status: "success",
})

const contentBlock = (content: string): ContentBlock => ({
  type: "content",
  content,
  contentType: "markdown",
})

function activityOf(blocks: unknown[]): WebActivityBlock {
  const activity = blocks[blocks.length - 1]
  if (!activity || (activity as { type?: unknown }).type !== "web_activity") {
    throw new Error("expected a trailing web_activity block")
  }
  return activity as WebActivityBlock
}

describe("appendWebActivityBlock over Chat MessageBlock lists", () => {
  it("groups a search/results/fetch burst into one trailing activity", () => {
    let blocks: MessageBlock[] = [contentBlock("Before the burst. ")]
    blocks = appendWebActivityBlock(
      blocks,
      webSearchBlock(),
      isWhitespaceContentBlock,
    )
    blocks = appendWebActivityBlock(
      blocks,
      webSearchResultsBlock(),
      isWhitespaceContentBlock,
    )
    blocks = appendWebActivityBlock(
      blocks,
      webFetchBlock(),
      isWhitespaceContentBlock,
    )

    expect(blocks.map((b) => b.type)).toEqual(["content", "web_activity"])
    expect(activityOf(blocks).items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: [
          { url: "https://example.com/weather", title: "Duluth weather" },
          { url: "https://example.org/forecast" },
        ],
        citedSources: [],
      },
      { kind: "fetch", url: "https://example.net/article", status: "success" },
    ])
  })

  it("drops a whitespace-only separator between carriers", () => {
    let blocks: MessageBlock[] = [contentBlock(" \n")]
    blocks = appendWebActivityBlock(
      blocks,
      webSearchBlock(),
      isWhitespaceContentBlock,
    )
    blocks = [...blocks, contentBlock(" ")]
    blocks = appendWebActivityBlock(
      blocks,
      webSearchResultsBlock(),
      isWhitespaceContentBlock,
    )

    expect(blocks.map((b) => b.type)).toEqual(["content", "web_activity"])
    expect(activityOf(blocks).items).toHaveLength(1)
  })

  it("ends the run when prose intervenes", () => {
    let blocks: MessageBlock[] = []
    blocks = appendWebActivityBlock(
      blocks,
      webSearchBlock(),
      isWhitespaceContentBlock,
    )
    blocks = [...blocks, contentBlock(" Some prose. ")]
    blocks = appendWebActivityBlock(
      blocks,
      webFetchBlock(),
      isWhitespaceContentBlock,
    )

    expect(blocks.map((b) => b.type)).toEqual([
      "web_activity",
      "content",
      "web_activity",
    ])
  })
})

describe("appendWebActivityBlock over MarkdownStream-shaped segments", () => {
  type StreamishSegment =
    | { text: string; trusted: boolean }
    | { type: "html_block" }
    | WebActivityBlock

  const isWhitespaceText = (segment: StreamishSegment): boolean =>
    !("type" in segment) && segment.text.trim() === ""

  it("groups adjacent web blocks and pairs results with the pending search", () => {
    let segments: StreamishSegment[] = [{ text: "Before. ", trusted: false }]
    segments = appendWebActivityBlock(
      segments,
      webSearchBlock(),
      isWhitespaceText,
    )
    segments = appendWebActivityBlock(
      segments,
      webSearchResultsBlock(),
      isWhitespaceText,
    )

    expect(segments).toHaveLength(2)
    const activity = activityOf(segments)
    expect(activity.items).toEqual([
      {
        kind: "search",
        query: "weather in Duluth",
        sources: [
          { url: "https://example.com/weather", title: "Duluth weather" },
          { url: "https://example.org/forecast" },
        ],
        citedSources: [],
      },
    ])
  })

  it("tolerates a whitespace-only text segment between carriers", () => {
    let segments: StreamishSegment[] = []
    segments = appendWebActivityBlock(
      segments,
      webSearchBlock(),
      isWhitespaceText,
    )
    segments = [...segments, { text: " \n", trusted: false }]
    segments = appendWebActivityBlock(
      segments,
      webFetchBlock(),
      isWhitespaceText,
    )

    expect(segments).toHaveLength(1)
    expect(activityOf(segments).items.map((it) => it.kind)).toEqual([
      "search",
      "fetch",
    ])
  })

  it("treats an html_block as a hard boundary that ends the run", () => {
    let segments: StreamishSegment[] = []
    segments = appendWebActivityBlock(
      segments,
      webSearchBlock(),
      isWhitespaceText,
    )
    segments = [...segments, { type: "html_block" }]
    segments = appendWebActivityBlock(
      segments,
      webFetchBlock(),
      isWhitespaceText,
    )

    expect(segments.map((s) => ("type" in s ? s.type : "text"))).toEqual([
      "web_activity",
      "html_block",
      "web_activity",
    ])
  })
})
