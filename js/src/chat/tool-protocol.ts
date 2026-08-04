import type { ContentType } from "../transport/types"
import { codeRanges } from "./markdown-code-ranges"

const TOOL_TAG_RE = /<shiny-tool-(request|result)\b/g
export const TOOL_MARKER = "<shiny-tool-"

// The content types whose text is server-authored markup worth scanning for
// tool elements. "text" means display literally, so tool markup in it is a
// sample rather than a call.
const ROUTABLE_CONTENT_TYPES: ReadonlySet<ContentType> = new Set([
  "markdown",
  "html",
])

export function isRoutableContentType(contentType: ContentType): boolean {
  return ROUTABLE_CONTENT_TYPES.has(contentType)
}

export function containsToolMarker(content: string): boolean {
  return content.includes(TOOL_MARKER)
}

interface ParsedToolElement {
  tag: "request" | "result"
  attrs: Record<string, string>
  start: number
  end: number
}

interface ToolEventSource {
  requestId: string
  toolName: string
  grouping?: "none" | "tool" | "all"
  intent?: string
  start: number
  end: number
}

export interface ToolRequestEvent extends ToolEventSource {
  kind: "request"
  definitionTitle?: string
  definitionIcon?: string
  arguments?: string
}

export interface ToolResultEvent extends ToolEventSource {
  kind: "result"
  title?: string
  icon?: string
  status: "success" | "error"
  label?: string
  valuePreview?: string
  value?: string
  valueType?: string
  requestCall?: string
  showRequest: boolean
  fullScreen: boolean
  expanded: boolean
  customDisplay: boolean
  footer?: string
}

export type ToolEvent = ToolRequestEvent | ToolResultEvent

const ATTR_RE =
  /([a-zA-Z_:][-a-zA-Z0-9_:.]*)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|(\S+)))?/g

// Attribute values reach the router still HTML-encoded. The browser decodes an
// attribute while parsing it, but this router parses attributes out of the raw
// content string itself, so the decoding is ours to do.
//
// Numeric references are not an edge case here: htmltools escapes a newline in
// an attribute value as `&#10;` in both languages. Decode `&amp;` last so an
// author writing the literal text "&#10;" is not double-decoded.
function decodeEntities(s: string): string {
  if (!s.includes("&")) return s
  return s
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#(\d+);/g, (m, dec: string) => codePointOr(m, parseInt(dec, 10)))
    .replace(/&#[xX]([0-9a-fA-F]+);/g, (m, hex: string) =>
      codePointOr(m, parseInt(hex, 16)),
    )
    .replace(/&amp;/g, "&")
}

// A reference outside Unicode range (or a surrogate) is not decodable; leave
// the original text rather than throwing or emitting a replacement character.
function codePointOr(original: string, code: number): string {
  if (!Number.isFinite(code) || code < 0 || code > 0x10ffff) return original
  if (code >= 0xd800 && code <= 0xdfff) return original
  return String.fromCodePoint(code)
}

// Find the `>` closing an open tag, skipping quoted attribute values (which may
// themselves contain `>`, such as an inline SVG icon).
function findOpenTagEnd(s: string, from: number): number {
  let quote: string | null = null
  for (let i = from; i < s.length; i++) {
    const c = s[i]
    if (quote) {
      if (c === quote) quote = null
    } else if (c === '"' || c === "'") {
      quote = c
    } else if (c === ">") {
      return i
    }
  }
  return -1
}

function parseAttributes(s: string): Record<string, string> {
  const attrs: Record<string, string> = {}
  ATTR_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = ATTR_RE.exec(s)) !== null) {
    if (m[0] === "") {
      ATTR_RE.lastIndex++
      continue
    }
    if (m[1] === undefined) continue
    const raw = m[2] ?? m[3] ?? m[4] ?? ""
    attrs[m[1].toLowerCase()] = decodeEntities(raw)
  }
  return attrs
}

function attrTruthy(attrs: Record<string, string>, name: string): boolean {
  if (!(name in attrs)) return false
  const v = attrs[name]
  return v === "" || v === "true"
}

function optionalTruthyAttribute(
  attrs: Record<string, string>,
  name: string,
): string | undefined {
  const value = attrs[name]
  return value ? value : undefined
}

function groupingAttribute(
  attrs: Record<string, string>,
): "none" | "tool" | "all" | undefined {
  const value = attrs["grouping"]
  return value === "none" || value === "tool" || value === "all"
    ? value
    : undefined
}

// Parse complete custom elements in order. A trailing incomplete element stops
// the scan and is left as prose until its closing tag arrives.
function parseToolElements(
  content: string,
  contentType: ContentType,
  shieldOpenFence = false,
): ParsedToolElement[] {
  const els: ParsedToolElement[] = []
  const isInsideFence =
    contentType === "markdown"
      ? codeRanges(content, shieldOpenFence)
      : () => false
  TOOL_TAG_RE.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = TOOL_TAG_RE.exec(content)) !== null) {
    if (isInsideFence(m.index)) continue
    const tag = m[1] as "request" | "result"
    const attrsStart = m.index + m[0].length
    const openEnd = findOpenTagEnd(content, attrsStart)
    if (openEnd === -1) break
    const closeTag = `</shiny-tool-${tag}>`
    const closeIdx = content.indexOf(closeTag, openEnd + 1)
    if (closeIdx === -1) break
    const end = closeIdx + closeTag.length
    els.push({
      tag,
      attrs: parseAttributes(content.slice(attrsStart, openEnd)),
      start: m.index,
      end,
    })
    TOOL_TAG_RE.lastIndex = end
  }
  return els
}

function normalizeToolElement(element: ParsedToolElement): ToolEvent {
  const { attrs } = element
  const grouping = groupingAttribute(attrs)
  const common = {
    requestId: attrs["request-id"] ?? "",
    toolName: attrs["tool-name"] ?? "",
    ...(grouping !== undefined ? { grouping } : {}),
    ...(attrs["intent"] !== undefined ? { intent: attrs["intent"] } : {}),
    start: element.start,
    end: element.end,
  }

  if (element.tag === "request") {
    return {
      kind: "request",
      ...common,
      ...(optionalTruthyAttribute(attrs, "tool-title") !== undefined
        ? { definitionTitle: optionalTruthyAttribute(attrs, "tool-title") }
        : {}),
      ...(optionalTruthyAttribute(attrs, "icon") !== undefined
        ? { definitionIcon: optionalTruthyAttribute(attrs, "icon") }
        : {}),
      ...(attrs["arguments"] !== undefined
        ? { arguments: attrs["arguments"] }
        : {}),
    }
  }

  return {
    kind: "result",
    ...common,
    ...(optionalTruthyAttribute(attrs, "tool-title") !== undefined
      ? { title: optionalTruthyAttribute(attrs, "tool-title") }
      : {}),
    ...(optionalTruthyAttribute(attrs, "icon") !== undefined
      ? { icon: optionalTruthyAttribute(attrs, "icon") }
      : {}),
    status: attrs["status"] === "error" ? "error" : "success",
    ...(attrs["label"] !== undefined ? { label: attrs["label"] } : {}),
    ...(attrs["value-preview"] !== undefined
      ? { valuePreview: attrs["value-preview"] }
      : {}),
    ...(attrs["value"] !== undefined ? { value: attrs["value"] } : {}),
    ...(optionalTruthyAttribute(attrs, "value-type") !== undefined
      ? { valueType: optionalTruthyAttribute(attrs, "value-type") }
      : {}),
    ...(attrs["request-call"] !== undefined
      ? { requestCall: attrs["request-call"] }
      : {}),
    showRequest: attrTruthy(attrs, "show-request"),
    fullScreen: attrTruthy(attrs, "full-screen"),
    expanded: attrTruthy(attrs, "expanded"),
    customDisplay: attrTruthy(attrs, "custom-display"),
    ...(attrs["footer"] !== undefined ? { footer: attrs["footer"] } : {}),
  }
}

export function parseToolEvents(
  content: string,
  contentType: ContentType,
  shieldOpenFence = false,
): ToolEvent[] {
  return parseToolElements(content, contentType, shieldOpenFence).map(
    normalizeToolElement,
  )
}
