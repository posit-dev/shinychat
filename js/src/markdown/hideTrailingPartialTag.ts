// Matches a trailing incomplete `<shiny-sidenote` opening tag: any prefix of
// "<shiny-sidenote" (each char past `<` optional), optionally followed by
// attribute text that contains no `<` or `>` (i.e. the closing `>` has not
// arrived). Anchored to end-of-string. Mirrors the nested-optional style of
// PARTIAL_SPAN_OPENING_RE in rehypeSuggestionCards.
const TRAILING_PARTIAL_SIDENOTE_RE =
  /<(s(h(i(n(y(-(s(i(d(e(n(o(t(e(\s[^<>]*)?)?)?)?)?)?)?)?)?)?)?)?)?)?)?$/

/**
 * During streaming, an unclosed opening tag is parsed as literal visible text.
 * Trim a trailing incomplete `<shiny-sidenote…` so it does not flash as raw
 * text; the next chunk that closes the tag restores it. A lone trailing `<`
 * is also withheld for one tick, which is harmless.
 */
export function hideTrailingPartialSidenoteTag(content: string): string {
  const m = content.match(TRAILING_PARTIAL_SIDENOTE_RE)
  if (!m || m[0] === "") return content
  return content.slice(0, content.length - m[0].length)
}
