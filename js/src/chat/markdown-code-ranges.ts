// Per CommonMark a fence may be indented up to 3 spaces (so an example nested
// in a list or blockquote still counts). Four or more leading spaces is an
// indented code block, not a fence, and is deliberately not matched here:
// recognizing one needs block context (blank lines, paragraph continuation)
// that this raw-string pass does not have.
const CODE_FENCE_OPEN_SRC = String.raw` {0,3}((\`|~)\2{2,}).*`
// A closed fence: the opener, then anything, then a closer that is *at least*
// as long as the opener — hence `\1\2*` rather than a bare `\1`, which would
// leave a ``` block closed by ```` open forever.
const CODE_FENCE_RE = new RegExp(
  `^${CODE_FENCE_OPEN_SRC}\n[\\s\\S]*?^ {0,3}\\1\\2*[ \t]*$`,
  "gm",
)
const CODE_FENCE_OPEN_RE = new RegExp(`^${CODE_FENCE_OPEN_SRC}$`, "gm")

// Code fence regions and inline code spans, whose contents are literal text and
// so must not be scanned for the custom elements we route on (<thinking>, tool
// tags): a message documenting those tags should render the example verbatim.
export function codeRanges(
  content: string,
  shieldOpenFence = false,
): (idx: number) => boolean {
  const ranges: Array<[number, number]> = []
  for (const m of content.matchAll(CODE_FENCE_RE)) {
    ranges.push([m.index, m.index + m[0].length])
  }
  // An *unclosed* fence runs to the end of the document per CommonMark, but we
  // only honor that for content we know came off a live stream, where a
  // trailing open fence is just the live cursor and there is no "rest of the
  // message" for it to swallow. Without this, a documented example flickers
  // into live tool UI for the moment between "<shiny-tool-result …>
  // </shiny-tool-result> emitted" and "closing fence emitted", because the
  // streaming path re-routes the whole accumulated block on every render.
  //
  // Applying the rule at finalize *unconditionally* stays rejected: real tool
  // elements arrive as `markdown` content blocks (preloaded/restored
  // transcripts concatenate a whole turn into one block), so one stray ``` in
  // prose would permanently suppress every real tool element after it — the
  // same risk that keeps code-span pairing to a single line.
  //
  // What finalize *may* do is pass the flag when the message it is finalizing
  // still has `insideFence` set. That flag is written only by the streaming tag
  // state machine, so it is never set on a preloaded/restored transcript (those
  // are built by `messagePayloadToData` and never touch the machine). It means
  // "this stream really did stop mid-fence" — a cancelled or truncated
  // response — so the example that was being documented stays prose instead of
  // popping into tool UI at the moment of finalization.
  if (shieldOpenFence) {
    const isClosed = (idx: number) =>
      ranges.some(([start, end]) => idx >= start && idx < end)
    for (const m of content.matchAll(CODE_FENCE_OPEN_RE)) {
      if (isClosed(m.index)) continue
      ranges.push([m.index, content.length])
      break
    }
  }

  // Inline code spans. Per CommonMark a span opens with a run of N backticks and
  // closes at the next run of exactly N, so a single-backtick pattern misses
  // ``…`` — which is precisely how you quote a sample containing a backtick.
  // Pairing is deliberately confined to one line: a stray unbalanced backtick is
  // common in prose, and a multi-line span would let two of them swallow a real
  // tool element (which the servers always emit on its own line).
  const runs: Array<[number, number]> = [...content.matchAll(/`+/g)].map(
    (m) => [m.index, m[0].length],
  )
  for (let i = 0; i < runs.length; i++) {
    const [start, len] = runs[i]!
    const lineEnd = content.indexOf("\n", start)
    const limit = lineEnd === -1 ? content.length : lineEnd
    for (let j = i + 1; j < runs.length && runs[j]![0] < limit; j++) {
      if (runs[j]![1] !== len) continue
      ranges.push([start, runs[j]![0] + runs[j]![1]])
      i = j
      break
    }
  }
  return (idx: number) =>
    ranges.some(([start, end]) => idx >= start && idx < end)
}
