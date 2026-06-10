import attachmentTypes from "./attachment-types.json"
import { uuid } from "../utils/uuid"

const utf8Decoder = new TextDecoder("utf-8")

export const SUPPORTED_IMAGE_TYPES = attachmentTypes.image_types

export type SupportedImageType = (typeof SUPPORTED_IMAGE_TYPES)[number]

export const SUPPORTED_PDF_TYPE = attachmentTypes.pdf_type

/**
 * Canonical MIME type for each accepted text-family file extension (lowercased,
 * no dot). Browsers report text/code MIME types inconsistently (often "" or
 * "text/plain"), so we resolve by extension and send a stable MIME downstream.
 */
export const TEXT_EXTENSION_TYPES: Record<string, string> =
  attachmentTypes.text_extensions

export const SUPPORTED_TEXT_TYPES: readonly string[] = Array.from(
  new Set(Object.values(TEXT_EXTENSION_TYPES)),
)

export type AttachmentFamily = "image" | "document" | "text"

interface AttachmentTypeSpec {
  family: AttachmentFamily
  /** Whether the image-downscale pipeline applies (images only). */
  downscale: boolean
}

/**
 * Supported upload MIME types and how to handle each. Adding a new type is a
 * localized change here (plus, for a new family, a render branch and a
 * server-side converter) — no new transport code.
 */
export const SUPPORTED_TYPES: Record<string, AttachmentTypeSpec> = {
  "image/png": { family: "image", downscale: true },
  "image/jpeg": { family: "image", downscale: true },
  "image/gif": { family: "image", downscale: true },
  "image/webp": { family: "image", downscale: true },
  [SUPPORTED_PDF_TYPE]: { family: "document", downscale: false },
  ...Object.fromEntries(
    SUPPORTED_TEXT_TYPES.map((t) => [t, { family: "text", downscale: false }]),
  ),
}

/** Default accept list when no `attachment-accept` attribute is provided. */
export const DEFAULT_UPLOAD_ACCEPT = Object.keys(SUPPORTED_TYPES)

/**
 * Build the file-input `accept` string. Includes the MIME types plus, for any
 * accepted text type, its file extensions (OS pickers do not reliably filter
 * text/code files by MIME alone).
 */
export function acceptAttribute(accept: readonly string[]): string {
  const tokens = new Set(accept)
  for (const [ext, mime] of Object.entries(TEXT_EXTENSION_TYPES)) {
    if (tokens.has(mime)) tokens.add(`.${ext}`)
  }
  return [...tokens].join(",")
}

/**
 * Longest-edge pixel limit. Images above this are downscaled before sending to
 * keep websocket payloads small (matches the useful resolution ceiling for
 * current vision models).
 */
export const MAX_IMAGE_EDGE = 1568

export interface AttachedFile {
  id: string
  /** MIME type, e.g. "image/png" or "application/pdf". */
  type: string
  family: AttachmentFamily
  /** Full data URL: `data:<mime>;base64,<data>`. */
  dataUrl: string
  /** Original file name (may be empty, e.g. for some pasted images). */
  name: string
  /** Decoded byte size of the (possibly downscaled) payload. */
  size: number
}

/** Slim form sent to the server and stored on a sent message. */
export interface AttachmentPayload {
  mime: string
  data_url: string
  name: string
  size: number
}

export function attachmentFamily(mime: string): AttachmentFamily | null {
  return SUPPORTED_TYPES[mime]?.family ?? null
}

export function isSupportedType(type: string): boolean {
  return type in SUPPORTED_TYPES
}

function isSupportedImageType(type: string): type is SupportedImageType {
  return (SUPPORTED_IMAGE_TYPES as readonly string[]).includes(type)
}

/**
 * Target dimensions when an image's longest edge exceeds `maxEdge`, preserving
 * aspect ratio. Returns `null` when no downscale is needed.
 */
export function computeDownscaledSize(
  width: number,
  height: number,
  maxEdge: number,
): { width: number; height: number } | null {
  const longest = Math.max(width, height)
  if (longest <= maxEdge) return null
  const scale = maxEdge / longest
  return {
    width: Math.round(width * scale),
    height: Math.round(height * scale),
  }
}

/** Default number of characters shown in a text-attachment preview. */
export const TEXT_PREVIEW_MAX_CHARS = 300

/**
 * Minimum pasted-text length (characters) that converts a clipboard paste into
 * a "Pasted Text" attachment card instead of inserting it into the textarea.
 */
export const PASTE_AS_FILE_MIN_CHARS = 1000

/** Decode a base64 string into its raw bytes. */
function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

/**
 * Decode a leading snippet of text from a base64 data URL for preview. Decodes
 * only a bounded prefix so a multi-megabyte file isn't fully decoded to show a
 * few lines. Returns "" on any decode failure or empty payload.
 */
export function previewText(dataUrl: string, maxChars: number): string {
  try {
    const comma = dataUrl.indexOf(",")
    if (comma === -1) return ""
    // 4 base64 chars -> 3 bytes; take enough to cover maxChars of multi-byte
    // UTF-8. Slicing at a multiple of 4 keeps the prefix valid base64.
    const b64 = dataUrl.slice(comma + 1, comma + 1 + maxChars * 4)
    if (b64.length === 0) return ""
    const text = utf8Decoder.decode(base64ToBytes(b64))
    const sliced = text.slice(0, maxChars)
    // A 4-byte char (e.g. emoji) is two UTF-16 code units; slicing at maxChars
    // can leave a lone high surrogate. The u flag makes the regex Unicode-aware
    // so it matches only unpaired surrogates, not valid pairs.
    return /[\uD800-\uDFFF]$/u.test(sliced) ? sliced.slice(0, -1) : sliced
  } catch {
    return ""
  }
}

/**
 * Decode the full UTF-8 text of a base64 data URL. Unlike previewText, this
 * decodes the entire payload — used by the lightbox to show complete file
 * content on demand. Returns "" on any decode failure or empty payload.
 */
export function decodeTextDataUrl(dataUrl: string): string {
  try {
    const comma = dataUrl.indexOf(",")
    if (comma === -1) return ""
    const b64 = dataUrl.slice(comma + 1)
    if (b64.length === 0) return ""
    return utf8Decoder.decode(base64ToBytes(b64))
  } catch {
    return ""
  }
}

/** Decode a base64 data URL into a Blob (used for iframe-friendly Blob URLs). */
export function dataUrlToBlob(dataUrl: string): Blob {
  const comma = dataUrl.indexOf(",")
  const header = comma === -1 ? "" : dataUrl.slice(0, comma)
  const mime = header.match(/data:([^;]+)/)?.[1] ?? "application/octet-stream"
  const bytes = base64ToBytes(comma === -1 ? "" : dataUrl.slice(comma + 1))
  return new Blob([bytes], { type: mime })
}

/** Decoded byte length of a base64 data URL (as produced by FileReader). */
export function dataUrlByteSize(dataUrl: string): number {
  const comma = dataUrl.indexOf(",")
  if (comma === -1) return 0
  const b64 = dataUrl.slice(comma + 1)
  if (b64.length === 0) return 0
  const padding = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0
  return Math.floor((b64.length * 3) / 4) - padding
}

/** Human-readable byte size for chips and notices. */
export function formatBytes(n: number): string {
  if (n < 1000) return `${n} B`
  const units = ["KB", "MB", "GB"]
  let v = n
  let i = -1
  do {
    v /= 1000
    i++
  } while (v >= 999.95 && i < units.length - 1)
  return `${v.toFixed(1)} ${units[i]}`
}

export function totalBytes(files: { size: number }[]): number {
  return files.reduce((sum, f) => sum + f.size, 0)
}

/** Read a File as a base64 data URL. */
function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}

/**
 * Downscale a data URL so its longest edge is <= MAX_IMAGE_EDGE. Returns the
 * (possibly unchanged) data URL and whether downscaling occurred. Falls back to
 * the original when canvas/image decoding is unavailable.
 */
async function downscaleDataUrl(
  dataUrl: string,
  mediaType: SupportedImageType,
): Promise<{ dataUrl: string; wasDownscaled: boolean }> {
  if (typeof document === "undefined" || typeof Image === "undefined") {
    return { dataUrl, wasDownscaled: false }
  }
  const img = await new Promise<HTMLImageElement | null>((resolve) => {
    const el = new Image()
    el.onload = () => resolve(el)
    el.onerror = () => resolve(null)
    el.src = dataUrl
  })
  if (!img || !img.naturalWidth || !img.naturalHeight) {
    return { dataUrl, wasDownscaled: false }
  }
  const size = computeDownscaledSize(
    img.naturalWidth,
    img.naturalHeight,
    MAX_IMAGE_EDGE,
  )
  if (!size) return { dataUrl, wasDownscaled: false }

  const canvas = document.createElement("canvas")
  canvas.width = size.width
  canvas.height = size.height
  const ctx = canvas.getContext("2d")
  if (!ctx) return { dataUrl, wasDownscaled: false }
  ctx.drawImage(img, 0, 0, size.width, size.height)
  const outType = mediaType === "image/gif" ? "image/png" : mediaType
  return { dataUrl: canvas.toDataURL(outType), wasDownscaled: true }
}

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".")
  return dot <= 0 ? "" : name.slice(dot + 1).toLowerCase()
}

/**
 * Short uppercase badge label for a PDF/document attachment chip, derived from
 * the file extension (e.g. "PDF", "MD", "PY"). Falls back to a type-based
 * label when the name has no extension.
 */
export function attachmentBadgeLabel(name: string, type: string): string {
  const ext = extensionOf(name)
  if (ext) return ext.toUpperCase()
  if (type === SUPPORTED_PDF_TYPE) return "PDF"
  return "FILE"
}

/**
 * Synthetic File for a large clipboard text paste. Named "Pasted Text" so the
 * attachment card and the server-side `<file-attachment name=...>` wrapper both
 * read nicely; typed text/plain so it round-trips like an uploaded .txt.
 */
export function pastedTextFile(text: string): File {
  return new File([text], "Pasted Text", { type: "text/plain" })
}

/**
 * Resolve a file's effective MIME type: trust a supported image/PDF MIME,
 * otherwise fall back to the file extension (text/code files report MIME
 * unreliably). Returns null when the type cannot be recognized.
 */
function resolveType(file: File): string | null {
  if (isSupportedImageType(file.type) || file.type === SUPPORTED_PDF_TYPE) {
    return file.type
  }
  const ext = extensionOf(file.name)
  if (ext) return TEXT_EXTENSION_TYPES[ext] ?? null
  // No extension: trust an accurate text MIME (e.g. a synthetic pasted-text
  // File). Real files often report "" for text/code, so the extension lookup
  // above remains the primary path.
  if (SUPPORTED_TEXT_TYPES.includes(file.type)) {
    return file.type
  }
  return null
}

/**
 * Convert a File into an AttachedFile. Returns null when the type is not in the
 * accept list or is unsupported. Images are downscaled; other types pass through
 * as their raw data URL.
 */
export async function processFile(
  file: File,
  accept: readonly string[],
): Promise<{
  file: AttachedFile
  wasDownscaled: boolean
  /** True when the source format was re-encoded (a downscaled GIF becomes a
   * still PNG; canvas cannot emit GIF), so animation is lost. */
  wasConverted: boolean
} | null> {
  const type = resolveType(file)
  if (type === null || !accept.includes(type)) return null
  const family = attachmentFamily(type)
  if (family === null) return null

  const spec = SUPPORTED_TYPES[type]
  const original = await fileToDataUrl(file)

  if (spec?.downscale && isSupportedImageType(type)) {
    const { dataUrl, wasDownscaled } = await downscaleDataUrl(original, type)
    const outType = wasDownscaled && type === "image/gif" ? "image/png" : type
    return {
      file: {
        id: uuid(),
        type: outType,
        family,
        dataUrl,
        name: file.name,
        size: dataUrlByteSize(dataUrl),
      },
      wasDownscaled,
      wasConverted: outType !== type,
    }
  }

  return {
    file: {
      id: uuid(),
      type,
      family,
      dataUrl: original,
      name: file.name,
      size: dataUrlByteSize(original),
    },
    wasDownscaled: false,
    wasConverted: false,
  }
}
