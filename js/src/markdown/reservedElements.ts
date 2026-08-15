/**
 * Element names that take content out of React and into raw HTML.
 *
 * `shiny-chat-raw-html` (and its legacy alias `shinychat-raw-html`) is
 * assigned to `innerHTML` by `RawHTML`; the two tool elements carry
 * attributes (`icon`, `footer`, `tool-name`, `value` with `value-type="html"`)
 * that reach `dangerouslySetInnerHTML`. Every other component in the tag maps
 * renders through React and is inert.
 *
 * The server only ever emits these from `split_html_islands()` and the
 * tool-card tagifier, which run when an app passes htmltools/Shiny UI rather
 * than a string — and that content is always labelled `content_type: "html"`.
 * So in markdown-parsed content these names are never legitimate, and content
 * that names them there is model output trying to reach a raw-HTML sink.
 */
export const RESERVED_ELEMENTS = [
  "shiny-chat-raw-html",
  "shinychat-raw-html",
  "shiny-tool-request",
  "shiny-tool-result",
] as const

// Case-insensitive because parse5 lowercases tag names, so `<SHINYCHAT-RAW-HTML>`
// would otherwise reach the sink. The lookahead requires a tag-name boundary so
// that longer names starting with a reserved one (`<shiny-tool-resultant>`) are
// left alone.
const RESERVED_ELEMENT_RE = new RegExp(
  `<(/?)(${RESERVED_ELEMENTS.join("|")})(?=[\\s/>]|$)`,
  "gi",
)

/**
 * Neutralize shinychat's raw-HTML element names so they render as visible text.
 *
 * Applied to markdown-parsed content only. Note that a reserved name inside a
 * code fence is escaped too, so it displays as `&lt;shinychat-raw-html>` rather
 * than `<shinychat-raw-html>`; fence-aware escaping would mean trusting fence
 * detection to decide what is safe, which is the wrong thing to depend on.
 */
export function escapeReservedElements(content: string): string {
  return content.replace(RESERVED_ELEMENT_RE, "&lt;$1$2")
}
