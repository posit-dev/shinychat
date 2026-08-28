import type {
  StructuredBlock,
  WebFetchBlock,
  WebSearchBlock,
  WebSearchResultsBlock,
  WebSearchSource,
} from "../transport/types"
import type { MessageBlock } from "./state"

/** The wire blocks that make up a web-activity burst. */
export type WebActivityWireBlock =
  | WebSearchBlock
  | WebSearchResultsBlock
  | WebFetchBlock

/** One cited/result source, shared by the wire and render models. */
export type WebActivitySource = WebSearchSource

export interface WebActivitySearchItem {
  kind: "search"
  query: string
  /** null while the search's results block hasn't arrived (or never will). */
  sources: WebSearchSource[] | null
  /**
   * Answer-citation fallback, populated only by the markup path
   * (rehypeAttachCitedSources collects citations onto the
   * <shiny-web-activity> wrapper; parseItems reads them onto the last
   * pending search). Structured blocks never carry it.
   */
  citedSources: WebSearchSource[]
}

export interface WebActivityFetchItem {
  kind: "fetch"
  url: string
  status?: string
}

export type WebActivityItem = WebActivitySearchItem | WebActivityFetchItem

/**
 * A run of adjacent web_* blocks grouped into one activity on arrival — the
 * structured re-expression of rehypeGroupWebActivity's wrapper. The group
 * wrapper never appears on the wire.
 */
export interface WebActivityBlock {
  type: "web_activity"
  items: WebActivityItem[]
}

/** Runtime check for the web_* discriminator set (the wire is JSON). */
export function isWebActivityWireBlock(
  block: StructuredBlock,
): block is WebActivityWireBlock {
  const type = (block as { type?: unknown }).type
  return (
    type === "web_search" ||
    type === "web_search_results" ||
    type === "web_fetch"
  )
}

/**
 * Defensively narrow a structured block to a supported web_* wire block.
 * `version` is a forward-compatibility marker: a block whose version this
 * client predates is ignored with a warning rather than breaking the
 * message around it (mirrors structuredBlockToLoop).
 */
export function asWebActivityWireBlock(
  block: StructuredBlock,
): WebActivityWireBlock | null {
  if (!isWebActivityWireBlock(block)) return null
  const version = (block as { version?: unknown }).version
  if (version !== 1) {
    console.warn(
      `Ignoring ${block.type} block with unsupported version: ${String(version)}`,
    )
    return null
  }
  return block
}

/**
 * Validate and dedupe (by URL) a sources payload. Shared by the structured
 * path (a real JSON array off the wire) and the markup path (a JSON string
 * attribute parsed by WebActivity's parseSources).
 */
export function normalizeSources(value: unknown): WebSearchSource[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  return value.filter((s): s is WebSearchSource => {
    if (!s || typeof (s as WebSearchSource).url !== "string") return false
    const url = (s as WebSearchSource).url
    if (seen.has(url)) return false
    seen.add(url)
    return true
  })
}

/**
 * Apply one web_* wire block to an activity, re-expressing
 * WebActivity.parseItems' adjacency pairing over structured arrival: a
 * results block attaches its sources to the earliest still-pending search
 * (parseItems' pending-search queue); one arriving with no pending search
 * becomes a query-less search item; a fetch block appends a standalone item.
 * The pending state lives in the items themselves (sources === null), so
 * pairing works across block_insert boundaries mid-stream.
 */
export function applyWebBlock(
  activity: WebActivityBlock | null,
  block: WebActivityWireBlock,
): WebActivityBlock {
  const items = [...(activity?.items ?? [])]
  if (block.type === "web_search") {
    items.push({
      kind: "search",
      query: block.query,
      sources: null,
      citedSources: [],
    })
  } else if (block.type === "web_search_results") {
    const sources = normalizeSources(block.sources)
    const pendingIndex = items.findIndex(
      (it) => it.kind === "search" && it.sources === null,
    )
    if (pendingIndex !== -1) {
      const pending = items[pendingIndex] as WebActivitySearchItem
      items[pendingIndex] = { ...pending, sources }
    } else {
      items.push({ kind: "search", query: "", sources, citedSources: [] })
    }
  } else {
    items.push({ kind: "fetch", url: block.url, status: block.status })
  }
  return { type: "web_activity", items }
}

/**
 * Append one web_* wire block to a message's block list, grouping it into
 * the trailing web activity when one is reachable — tolerating a
 * whitespace-only string segment between carriers, exactly as
 * rehypeGroupWebActivity tolerates whitespace text nodes (the whitespace is
 * dropped; any other block ends the run and starts a new activity). A lone
 * web block forms an activity on its own.
 */
export function appendWebActivityBlock(
  blocks: MessageBlock[],
  block: WebActivityWireBlock,
): MessageBlock[] {
  const out = [...blocks]
  let tail = out[out.length - 1]
  if (tail?.type === "content" && tail.content.trim() === "") {
    const prev = out[out.length - 2]
    if (prev?.type === "web_activity") {
      // The whitespace-only separator is part of the run; drop it.
      out.pop()
      tail = prev
    }
  }
  if (tail?.type === "web_activity") {
    out[out.length - 1] = applyWebBlock(tail, block)
  } else {
    out.push(applyWebBlock(null, block))
  }
  return out
}
