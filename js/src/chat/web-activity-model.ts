import type {
  StructuredBlock,
  WebFetchBlock,
  WebSearchBlock,
  WebSearchCitationsBlock,
  WebSearchResultsBlock,
  WebSearchSource,
} from "../transport/types"
import type { MessageBlock } from "./state"

/** The wire blocks that make up a web-activity burst. */
export type WebActivityWireBlock =
  | WebSearchBlock
  | WebSearchResultsBlock
  | WebSearchCitationsBlock
  | WebFetchBlock

/** One cited/result source, shared by the wire and render models. */
export type WebActivitySource = WebSearchSource

export interface WebActivitySearchItem {
  kind: "search"
  query: string
  /** Provider search id, when the wire block carried one. */
  id?: string
  /** null while the search's results block hasn't arrived (or never will). */
  sources: WebSearchSource[] | null
  /**
   * Citation fallback, shown only while no provider results are attached
   * (sources === null). Populated by `web_search_citations` blocks.
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
 * A run of adjacent web_* blocks grouped into one activity on arrival.
 * The group wrapper never appears on the wire.
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
    type === "web_search_citations" ||
    type === "web_fetch"
  )
}

/**
 * Narrow a structured block to a supported web_* wire block. Returns null
 * (with a warning) for an unsupported version or malformed block, so the
 * rest of the message renders.
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
  const required =
    block.type === "web_search"
      ? typeof (block as { query?: unknown }).query === "string"
      : block.type === "web_fetch"
        ? typeof (block as { url?: unknown }).url === "string"
        : Array.isArray((block as { sources?: unknown }).sources)
  if (!required) {
    console.warn(
      `Ignoring malformed ${block.type} block: required fields missing or mistyped`,
    )
    return null
  }
  return block
}

/** Validate and dedupe (by URL) a sources payload. */
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
 * Apply one web_* wire block to an activity. A results block attaches its
 * sources to the search named by `search_id`, or when no id was sent, to
 * the earliest still-pending search. One arriving with no matching search
 * becomes a query-less search item. A fetch block appends a standalone
 * item. The pending state lives in the items themselves (sources === null),
 * so pairing works across block_insert boundaries mid-stream.
 */
export function applyWebBlock(
  activity: WebActivityBlock | null,
  block: Exclude<WebActivityWireBlock, WebSearchCitationsBlock>,
): WebActivityBlock {
  const items = [...(activity?.items ?? [])]
  if (block.type === "web_search") {
    items.push({
      kind: "search",
      query: block.query,
      id: block.id,
      sources: null,
      citedSources: [],
    })
  } else if (block.type === "web_search_results") {
    const sources = normalizeSources(block.sources)
    // An unmatched search_id must not fall back to FIFO: attaching to an
    // unrelated pending search would misattribute the results.
    const index =
      block.search_id !== undefined
        ? items.findIndex(
            (it) => it.kind === "search" && it.id === block.search_id,
          )
        : items.findIndex((it) => it.kind === "search" && it.sources === null)
    if (index !== -1) {
      const search = items[index] as WebActivitySearchItem
      items[index] = { ...search, sources }
    } else {
      items.push({ kind: "search", query: "", sources, citedSources: [] })
    }
  } else if (block.type === "web_fetch") {
    items.push({ kind: "fetch", url: block.url, status: block.status })
  }
  return { type: "web_activity", items }
}

/**
 * Merge cited sources into a search item's fallback list, by URL. First
 * occurrence wins; a later title backfills a missing one.
 */
function mergeCitedSources(
  existing: WebSearchSource[],
  incoming: WebSearchSource[],
): WebSearchSource[] {
  const byUrl = new Map(existing.map((s) => [s.url, s]))
  for (const source of incoming) {
    const current = byUrl.get(source.url)
    if (current === undefined) {
      byUrl.set(source.url, source)
    } else if (current.title === undefined && source.title !== undefined) {
      byUrl.set(source.url, { ...current, title: source.title })
    }
  }
  return [...byUrl.values()]
}

/**
 * Apply a citations block to the most recent search item in the list,
 * walking back across activities and intervening content. The block
 * renders nothing itself, so the list shape is unchanged when no search
 * exists to receive the sources.
 */
function applyWebCitations<T>(
  blocks: (T | WebActivityBlock)[],
  block: WebSearchCitationsBlock,
): (T | WebActivityBlock)[] {
  const sources = normalizeSources(block.sources)
  if (sources.length === 0) return blocks
  for (let i = blocks.length - 1; i >= 0; i--) {
    const candidate = blocks[i]
    if (!isWebActivityBlock(candidate)) continue
    const items = [...candidate.items]
    for (let j = items.length - 1; j >= 0; j--) {
      const item = items[j]
      if (item === undefined || item.kind !== "search") continue
      items[j] = {
        ...item,
        citedSources: mergeCitedSources(item.citedSources, sources),
      }
      const out = [...blocks]
      out[i] = { ...candidate, items }
      return out
    }
  }
  return blocks
}

/** Structural check for a grouped web-activity block in any block list. */
function isWebActivityBlock(block: unknown): block is WebActivityBlock {
  return (
    typeof block === "object" &&
    block !== null &&
    (block as { type?: unknown }).type === "web_activity"
  )
}

/** Whitespace-only content block between web_* carriers is part of the run. */
export function isWhitespaceContentBlock(
  block: MessageBlock | WebActivityBlock,
): boolean {
  return block.type === "content" && block.content.trim() === ""
}

/**
 * Append one web_* wire block to a block list, grouping into the trailing
 * web activity when reachable. Tolerates a whitespace-only separator
 * (dropped; any other block ends the run). A citations block is the
 * exception: it renders nothing and instead updates the most recent search
 * item wherever it sits, so it neither joins nor breaks the adjacency run.
 * Generic over the list's entry shape so Chat (MessageBlock[]) and
 * MarkdownStream (StreamSegment[]) share one implementation.
 */
export function appendWebActivityBlock<T>(
  blocks: (T | WebActivityBlock)[],
  block: WebActivityWireBlock,
  isWhitespaceText: (block: T | WebActivityBlock) => boolean,
): (T | WebActivityBlock)[] {
  if (block.type === "web_search_citations") {
    return applyWebCitations(blocks, block)
  }
  const out: (T | WebActivityBlock)[] = [...blocks]
  let tail = out[out.length - 1]
  if (tail !== undefined && isWhitespaceText(tail)) {
    const prev = out[out.length - 2]
    if (isWebActivityBlock(prev)) {
      out.pop()
      tail = prev
    }
  }
  if (isWebActivityBlock(tail)) {
    out[out.length - 1] = applyWebBlock(tail, block)
  } else {
    out.push(applyWebBlock(null, block))
  }
  return out
}
