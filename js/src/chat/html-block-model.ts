import type {
  HtmlDep,
  StructuredBlock,
  HtmlBlock as HtmlBlockWire,
} from "../transport/types"

/**
 * Render-model form of a structured `html_block`: a server-authored
 * raw-HTML island. Shared by Chat (message blocks) and MarkdownStream
 * (stream segments).
 */
export interface HtmlBlock {
  type: "html_block"
  content: string
  contentType: "html"
  /** Block-level deps, rendered before the island's HTML mounts. */
  htmlDeps: HtmlDep[]
}

/**
 * Defensively narrow a structured block to a supported `html_block` wire
 * block. A block whose version this client predates is ignored with a
 * warning rather than breaking the message around it.
 */
export function asHtmlBlock(block: StructuredBlock): HtmlBlockWire | null {
  if ((block as { type?: unknown }).type !== "html_block") return null
  const version = (block as { version?: unknown }).version
  if (version !== 1) {
    console.warn(
      `Ignoring html_block block with unsupported version: ${String(version)}`,
    )
    return null
  }
  if (typeof (block as { content?: unknown }).content !== "string") {
    console.warn(
      "Ignoring malformed html_block block: content must be a string",
    )
    return null
  }
  return block as HtmlBlockWire
}

/** Convert a validated `html_block` wire block to its render-model form. */
export function htmlBlockToRenderBlock(block: HtmlBlockWire): HtmlBlock {
  return {
    type: "html_block",
    content: block.content,
    contentType: "html",
    htmlDeps: block.html_deps ?? [],
  }
}
