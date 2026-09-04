/**
 * Rewrites selected HTML end tags with a single monotonic scan.
 *
 * This follows the tokenizer states that affect tag recognition rather than
 * trying to encode HTML's permissive grammar in a regular expression.
 */

const RAW_TEXT_TAGS = new Set([
  "iframe",
  "noembed",
  "noframes",
  "script",
  "style",
  "xmp",
])
const RCDATA_TAGS = new Set(["textarea", "title"])

function isHtmlWhitespace(c: string): boolean {
  return c === " " || c === "\t" || c === "\n" || c === "\f" || c === "\r"
}

function isAsciiAlpha(c: string): boolean {
  const code = c.charCodeAt(0)
  return (code >= 65 && code <= 90) || (code >= 97 && code <= 122)
}

function asciiLower(value: string): string {
  let result = ""
  for (let i = 0; i < value.length; i++) {
    const code = value.charCodeAt(i)
    result += String.fromCharCode(code >= 65 && code <= 90 ? code + 32 : code)
  }
  return result
}

function isTagNameEnd(c: string): boolean {
  return c === "" || isHtmlWhitespace(c) || c === "/" || c === ">"
}

type TagEnd = {
  end: number
  selfClosingSlash: number | null
}

/**
 * Scan from immediately after a tag name through the tokenizer's attribute
 * states. End-tag attributes are parse errors, but browsers still tokenize
 * them and emit the end tag.
 */
function scanTagEnd(value: string, pos: number): TagEnd | null {
  let i = pos

  while (i < value.length) {
    const c = value.charAt(i)
    if (isHtmlWhitespace(c)) {
      i++
      continue
    }
    if (c === ">") return { end: i, selfClosingSlash: null }
    if (c === "/") {
      const slash = i
      i++
      if (value.charAt(i) === ">") {
        return { end: i, selfClosingSlash: slash }
      }
      continue
    }

    // Attribute name. Even a leading '=' is consumed as the first character.
    i++
    while (
      i < value.length &&
      !isHtmlWhitespace(value.charAt(i)) &&
      value.charAt(i) !== "/" &&
      value.charAt(i) !== ">" &&
      value.charAt(i) !== "="
    ) {
      i++
    }

    while (i < value.length && isHtmlWhitespace(value.charAt(i))) i++
    if (value.charAt(i) !== "=") continue

    i++
    while (i < value.length && isHtmlWhitespace(value.charAt(i))) i++
    const quote = value.charAt(i)
    if (quote === '"' || quote === "'") {
      i++
      while (i < value.length && value.charAt(i) !== quote) i++
      if (i >= value.length) return null
      i++
      continue
    }

    // Quotes, apostrophes, '<', '=', and '/' are parse errors but literal
    // characters in an unquoted value.
    while (
      i < value.length &&
      !isHtmlWhitespace(value.charAt(i)) &&
      value.charAt(i) !== ">"
    ) {
      i++
    }
  }

  return null
}

function readTagName(
  value: string,
  pos: number,
): { name: string; end: number } {
  let i = pos
  while (!isTagNameEnd(value.charAt(i))) i++
  return { name: asciiLower(value.slice(pos, i)), end: i }
}

function skipComment(value: string, pos: number): number {
  // COMMENT_START and COMMENT_START_DASH both close abruptly on `>`.
  if (value.charAt(pos) === ">") return pos + 1
  if (value.charAt(pos) === "-" && value.charAt(pos + 1) === ">") {
    return pos + 2
  }

  let i = pos
  while (i < value.length) {
    const end = value.indexOf("--", i)
    if (end === -1) return value.length
    const next = value.charAt(end + 2)
    if (next === ">") return end + 3
    if (next === "!" && value.charAt(end + 3) === ">") return end + 4
    i = end + 2
  }
  return value.length
}

function skipBogusComment(value: string, pos: number): number {
  const end = value.indexOf(">", pos)
  return end === -1 ? value.length : end + 1
}

/**
 * Raw-text and RCDATA elements only recognize an appropriate end tag.
 * Everything else, including a reserved-island spelling, is text.
 */
function skipRawText(value: string, pos: number, tagName: string): number {
  let i = pos
  while (i < value.length) {
    const at = value.indexOf("</", i)
    if (at === -1) return value.length
    const name = readTagName(value, at + 2)
    if (name.name === tagName) {
      const tagEnd = scanTagEnd(value, name.end)
      if (tagEnd) return tagEnd.end + 1
      return value.length
    }
    i = at + 2
  }
  return value.length
}

/**
 * Replace emitted `</tag ...>` tokens with `replacement`.
 *
 * Matching is ASCII-case-insensitive, like the HTML tokenizer. Candidates in
 * comments, attributes, and raw-text elements are ignored. The scan never
 * moves backwards, so runtime is O(value.length).
 */
export function rewriteEndTagsHtml(
  value: string,
  tag: string,
  replacement: string,
): string {
  return rewriteTagsHtml(value, {
    [asciiLower(tag)]: { end: replacement },
  })
}

export type HtmlTagRewrite = {
  /** Replacement for `<tag`, preserving the original attribute text. */
  start?: string
  /** Replacement for the complete emitted end tag. */
  end?: string
  /** Appended after `>` when a start tag carries a tokenizer-recognized `/`. */
  selfClosingEnd?: string
}

/**
 * Rewrite emitted start and end tags in one tokenizer-aware pass.
 *
 * Object keys must be lowercase ASCII tag names. Start-tag replacements only
 * replace `<tag`; attributes remain byte-for-byte intact. For a tokenizer-
 * recognized self-closing start tag, `/>` is normalized to `>` plus
 * `selfClosingEnd`, preventing a non-void replacement element from swallowing
 * the following document.
 */
export function rewriteTagsHtml(
  value: string,
  rewrites: Readonly<Record<string, HtmlTagRewrite>>,
): string {
  const replacements: { start: number; end: number; value: string }[] = []
  let i = 0

  while (i < value.length) {
    const open = value.indexOf("<", i)
    if (open === -1) break

    if (value.startsWith("<!--", open)) {
      i = skipComment(value, open + 4)
      continue
    }

    const next = value.charAt(open + 1)
    if (next === "!" || next === "?") {
      i = skipBogusComment(value, open + 2)
      continue
    }

    const isEndTag = next === "/"
    const nameStart = open + (isEndTag ? 2 : 1)
    const firstNameChar = value.charAt(nameStart)
    if (!isAsciiAlpha(firstNameChar)) {
      // Invalid end-tag openers become bogus comments through the next `>`.
      // Invalid start-tag openers emit `<` as text, so a later `<` remains
      // eligible to open a real tag.
      if (isEndTag) {
        i = skipBogusComment(value, nameStart)
        continue
      }
      i = open + 1
      continue
    }

    const name = readTagName(value, nameStart)
    const tagEnd = scanTagEnd(value, name.end)
    if (!tagEnd) {
      // This emitted tag consumes the remaining input without reaching '>'.
      break
    }

    const rewrite = rewrites[name.name]
    if (isEndTag && rewrite?.end !== undefined) {
      replacements.push({
        start: open,
        end: tagEnd.end + 1,
        value: rewrite.end,
      })
    } else if (!isEndTag && rewrite?.start !== undefined) {
      replacements.push({
        start: open,
        end: name.end,
        value: rewrite.start,
      })
      if (
        tagEnd.selfClosingSlash !== null &&
        rewrite.selfClosingEnd !== undefined
      ) {
        replacements.push({
          start: tagEnd.selfClosingSlash,
          end: tagEnd.end + 1,
          value: `>${rewrite.selfClosingEnd}`,
        })
      }
    }

    i = tagEnd.end + 1
    if (
      !isEndTag &&
      (RAW_TEXT_TAGS.has(name.name) || RCDATA_TAGS.has(name.name))
    ) {
      i = skipRawText(value, i, name.name)
    } else if (!isEndTag && name.name === "plaintext") {
      break
    }
  }

  if (replacements.length === 0) return value

  const result: string[] = []
  let copiedThrough = 0
  for (const match of replacements) {
    result.push(value.slice(copiedThrough, match.start), match.value)
    copiedThrough = match.end
  }
  result.push(value.slice(copiedThrough))
  return result.join("")
}
