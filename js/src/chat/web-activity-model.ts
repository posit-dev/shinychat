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
   * Answer-citation fallback, shown only while no provider results attach
   * (sources === null). Populated on the markup path by
   * rehypeAttachCitedSources (citations collected onto the
   * <shiny-web-activity> wrapper; parseItems reads them onto the last
   * pending search) or on the structured path by a web_search block's
   * `cited_sources`.
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
      // Answer-citation fallback carried explicitly on the block. A later
      // results block's sources still win: the UI reads
      // `sources ?? citedSources`.
      citedSources: normalizeSources(block.cited_sources),
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

/** Structural check for a grouped web-activity block in any block list. */
function isWebActivityBlock(block: unknown): block is WebActivityBlock {
  return (
    typeof block === "object" &&
    block !== null &&
    (block as { type?: unknown }).type === "web_activity"
  )
}

/**
 * Chat's whitespace-separator check: a whitespace-only content block
 * between web_* carriers is part of the run (dropped on grouping),
 * mirroring rehypeGroupWebActivity's tolerance of whitespace text nodes.
 */
export function isWhitespaceContentBlock(
  block: MessageBlock | WebActivityBlock,
): boolean {
  return block.type === "content" && block.content.trim() === ""
}

/**
 * Append one web_* wire block to a block list, grouping it into the
 * trailing web activity when one is reachable — tolerating a
 * whitespace-only string segment between carriers, exactly as
 * rehypeGroupWebActivity tolerates whitespace text nodes (the whitespace is
 * dropped; any other block ends the run and starts a new activity). A lone
 * web block forms an activity on its own.
 *
 * Generic over the list's entry shape so Chat (MessageBlock[]) and
 * MarkdownStream (StreamSegment[]) share the one grouping/pairing
 * implementation; `isWhitespaceText` identifies a droppable whitespace
 * separator in the caller's shape (e.g. isWhitespaceContentBlock for Chat).
 */
export function appendWebActivityBlock<T>(
  blocks: (T | WebActivityBlock)[],
  block: WebActivityWireBlock,
  isWhitespaceText: (block: T | WebActivityBlock) => boolean,
): (T | WebActivityBlock)[] {
  const out: (T | WebActivityBlock)[] = [...blocks]
  let tail = out[out.length - 1]
  if (tail !== undefined && isWhitespaceText(tail)) {
    const prev = out[out.length - 2]
    if (isWebActivityBlock(prev)) {
      // The whitespace-only separator is part of the run; drop it.
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
