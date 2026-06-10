import { describe, it, expect } from "vitest"
import {
  SUPPORTED_IMAGE_TYPES,
  SUPPORTED_PDF_TYPE,
  SUPPORTED_TYPES,
  SUPPORTED_TEXT_TYPES,
  TEXT_EXTENSION_TYPES,
  DEFAULT_UPLOAD_ACCEPT,
  MAX_IMAGE_EDGE,
  attachmentFamily,
  isSupportedType,
  computeDownscaledSize,
  dataUrlByteSize,
  formatBytes,
  totalBytes,
  processFile,
  acceptAttribute,
  attachmentBadgeLabel,
  previewText,
  PASTE_AS_FILE_MIN_CHARS,
  pastedTextFile,
  decodeTextDataUrl,
} from "../../src/chat/attachments"

describe("attachmentFamily", () => {
  it("classifies images and pdf", () => {
    expect(attachmentFamily("image/png")).toBe("image")
    expect(attachmentFamily("application/pdf")).toBe("document")
  })
  it("returns text for text/plain", () => {
    expect(attachmentFamily("text/plain")).toBe("text")
  })
  it("returns null for unsupported types", () => {
    expect(attachmentFamily("image/svg+xml")).toBeNull()
    expect(attachmentFamily("")).toBeNull()
  })
  it("classifies json and ipynb as the text family", () => {
    expect(attachmentFamily("application/json")).toBe("text")
    expect(attachmentFamily("application/x-ipynb+json")).toBe("text")
  })
})

describe("isSupportedType", () => {
  it("accepts images and pdf, rejects others", () => {
    expect(isSupportedType("image/webp")).toBe(true)
    expect(isSupportedType("application/pdf")).toBe(true)
    expect(isSupportedType("image/svg+xml")).toBe(false)
  })
})

describe("constants", () => {
  it("default accept includes images and pdf", () => {
    for (const t of SUPPORTED_IMAGE_TYPES) {
      expect(DEFAULT_UPLOAD_ACCEPT).toContain(t)
    }
    expect(DEFAULT_UPLOAD_ACCEPT).toContain(SUPPORTED_PDF_TYPE)
  })
  it("maps pdf to the document family without downscaling", () => {
    expect(SUPPORTED_TYPES["application/pdf"]).toEqual({
      family: "document",
      downscale: false,
    })
  })
})

describe("computeDownscaledSize", () => {
  it("returns null within the limit", () => {
    expect(computeDownscaledSize(800, 600, MAX_IMAGE_EDGE)).toBeNull()
  })
  it("scales the longest edge, preserving aspect ratio", () => {
    expect(computeDownscaledSize(3136, 1568, MAX_IMAGE_EDGE)).toEqual({
      width: MAX_IMAGE_EDGE,
      height: 784,
    })
  })
  it("handles portrait orientation", () => {
    expect(computeDownscaledSize(784, 3136, MAX_IMAGE_EDGE)).toEqual({
      width: 392,
      height: MAX_IMAGE_EDGE,
    })
  })
  it("returns null at the exact boundary", () => {
    expect(
      computeDownscaledSize(MAX_IMAGE_EDGE, MAX_IMAGE_EDGE, MAX_IMAGE_EDGE),
    ).toBeNull()
  })
})

describe("dataUrlByteSize", () => {
  it("decodes the byte length from a base64 data URL", () => {
    // "hello" base64 = "aGVsbG8=" -> 5 bytes
    expect(dataUrlByteSize("data:text/plain;base64,aGVsbG8=")).toBe(5)
  })
})

describe("formatBytes", () => {
  it("formats bytes, KB, MB", () => {
    expect(formatBytes(500)).toBe("500 B")
    expect(formatBytes(2_400_000)).toBe("2.4 MB")
  })
  it("advances the unit at the rounding boundary", () => {
    expect(formatBytes(999_999)).toBe("1.0 MB")
  })
})

describe("totalBytes", () => {
  it("sums the size field", () => {
    expect(totalBytes([{ size: 100 } as never, { size: 250 } as never])).toBe(
      350,
    )
  })
})

describe("text types", () => {
  it("registers text types as the text family without downscaling", () => {
    for (const mime of SUPPORTED_TEXT_TYPES) {
      expect(SUPPORTED_TYPES[mime]).toEqual({
        family: "text",
        downscale: false,
      })
    }
  })
  it("maps common extensions to canonical MIME types", () => {
    expect(TEXT_EXTENSION_TYPES["md"]).toBe("text/markdown")
    expect(TEXT_EXTENSION_TYPES["qmd"]).toBe("text/markdown")
    expect(TEXT_EXTENSION_TYPES["ipynb"]).toBe("application/x-ipynb+json")
    expect(TEXT_EXTENSION_TYPES["r"]).toBe("text/x-r")
  })
  it("default accept includes the text MIME types", () => {
    for (const mime of SUPPORTED_TEXT_TYPES) {
      expect(DEFAULT_UPLOAD_ACCEPT).toContain(mime)
    }
  })
})

describe("acceptAttribute", () => {
  it("includes MIME types plus extensions for text types in the accept list", () => {
    const out = acceptAttribute(["image/png", "text/markdown"])
    const tokens = out.split(",")
    expect(tokens).toContain("image/png")
    expect(tokens).toContain("text/markdown")
    expect(tokens).toContain(".md")
    expect(tokens).toContain(".markdown")
  })
  it("omits extensions whose MIME is not accepted", () => {
    const out = acceptAttribute(["image/png"])
    expect(out.split(",")).not.toContain(".md")
  })
  it("includes every text extension when the full default accept list is used", () => {
    const tokens = acceptAttribute(DEFAULT_UPLOAD_ACCEPT).split(",")
    for (const ext of Object.keys(TEXT_EXTENSION_TYPES)) {
      expect(tokens).toContain(`.${ext}`)
    }
  })
})

describe("processFile", () => {
  it("returns null when the type is not in the accept list", async () => {
    const file = new File(["x"], "doc.pdf", { type: "application/pdf" })
    expect(await processFile(file, ["image/png"])).toBeNull()
  })
  it("processes a PDF as a document with the raw data URL", async () => {
    const file = new File(["%PDF-1.4 test"], "report.pdf", {
      type: "application/pdf",
    })
    const result = await processFile(file, DEFAULT_UPLOAD_ACCEPT)
    expect(result).not.toBeNull()
    expect(result!.file.family).toBe("document")
    expect(result!.file.type).toBe("application/pdf")
    expect(result!.file.name).toBe("report.pdf")
    expect(result!.file.dataUrl.startsWith("data:application/pdf")).toBe(true)
    expect(result!.file.size).toBeGreaterThan(0)
    expect(result!.wasDownscaled).toBe(false)
  })
  it("resolves a text file by extension when the browser MIME is empty", async () => {
    const file = new File(["# Title\n"], "notes.md", { type: "" })
    const result = await processFile(file, DEFAULT_UPLOAD_ACCEPT)
    expect(result).not.toBeNull()
    expect(result!.file.type).toBe("text/markdown")
    expect(result!.file.family).toBe("text")
    expect(result!.file.name).toBe("notes.md")
    expect(result!.file.dataUrl.startsWith("data:")).toBe(true)
    expect(result!.file.size).toBeGreaterThan(0)
    expect(result!.wasDownscaled).toBe(false)
  })
  it("resolves Quarto and Jupyter extensions", async () => {
    // browser reports text/plain, but the .qmd extension wins
    const qmd = new File(["---\n"], "report.qmd", { type: "text/plain" })
    expect((await processFile(qmd, DEFAULT_UPLOAD_ACCEPT))!.file.type).toBe(
      "text/markdown",
    )
    const ipynb = new File(["{}"], "nb.ipynb", { type: "" })
    expect((await processFile(ipynb, DEFAULT_UPLOAD_ACCEPT))!.file.type).toBe(
      "application/x-ipynb+json",
    )
  })
  it("returns null for an unrecognized extension", async () => {
    const file = new File(["x"], "thing.exe", { type: "" })
    expect(await processFile(file, DEFAULT_UPLOAD_ACCEPT)).toBeNull()
  })
  it("returns null when the resolved text type is not in the accept list", async () => {
    const file = new File(["x"], "notes.md", { type: "" })
    expect(await processFile(file, ["image/png"])).toBeNull()
  })
  it("treats a dotfile with no stem as having no extension", async () => {
    const file = new File(["echo hi"], ".sh", { type: "" })
    expect(await processFile(file, DEFAULT_UPLOAD_ACCEPT)).toBeNull()
  })
  it("resolves an R Markdown (.rmd) file to text/markdown", async () => {
    const file = new File(["---\n"], "report.rmd", { type: "" })
    expect((await processFile(file, DEFAULT_UPLOAD_ACCEPT))!.file.type).toBe(
      "text/markdown",
    )
  })
})

describe("previewText", () => {
  const url = (s: string) => `data:text/plain;base64,${btoa(s)}`
  it("decodes text from a base64 data URL", () => {
    expect(previewText(url("hello world"), 300)).toBe("hello world")
  })
  it("truncates to maxChars", () => {
    expect(previewText(url("hello world"), 5)).toBe("hello")
  })
  it("returns empty string for a data URL with no payload", () => {
    expect(previewText("data:text/plain;base64,", 300)).toBe("")
  })
  it("returns empty string for a malformed data URL", () => {
    expect(previewText("not a data url", 300)).toBe("")
  })
  it("handles multibyte UTF-8 without throwing and round-trips full content", () => {
    const emoji = "Hello 🌍 world"
    const bytes = new TextEncoder().encode(emoji)
    const b64 = btoa(String.fromCharCode(...bytes))
    const multibyteUrl = `data:text/plain;base64,${b64}`
    expect(() => previewText(multibyteUrl, 8)).not.toThrow()
    expect(previewText(multibyteUrl, 300)).toBe(emoji)
  })
  it("does not return a lone surrogate when slicing between a surrogate pair", () => {
    const emojis = "😀".repeat(50) // each emoji = 2 UTF-16 code units
    const bytes = new TextEncoder().encode(emojis)
    let bin = ""
    for (const b of bytes) bin += String.fromCharCode(b)
    const dataUrl = `data:text/plain;base64,${btoa(bin)}`
    const out = previewText(dataUrl, 5) // odd boundary relative to pairs
    // u flag makes the regex Unicode-aware: matches lone surrogates, not valid pairs
    expect(/[\uD800-\uDFFF]$/u.test(out)).toBe(false)
  })
})

describe("pastedTextFile", () => {
  it("builds a text/plain File named 'Pasted Text'", () => {
    const f = pastedTextFile("hello world")
    expect(f.name).toBe("Pasted Text")
    expect(f.type).toBe("text/plain")
    expect(f.size).toBe(11)
  })

  it("exports the 1000-character threshold", () => {
    expect(PASTE_AS_FILE_MIN_CHARS).toBe(1000)
  })

  it("processFile resolves a no-extension text/plain File to the text family", async () => {
    const file = pastedTextFile("x".repeat(1500))
    const result = await processFile(file, ["text/plain"])
    expect(result).not.toBeNull()
    expect(result!.file.family).toBe("text")
    expect(result!.file.type).toBe("text/plain")
    expect(result!.file.name).toBe("Pasted Text")
  })
})

describe("attachmentBadgeLabel", () => {
  it("uppercases the file extension", () => {
    expect(attachmentBadgeLabel("report.pdf", "application/pdf")).toBe("PDF")
    expect(attachmentBadgeLabel("notes.md", "text/markdown")).toBe("MD")
    expect(attachmentBadgeLabel("analysis.py", "text/x-python")).toBe("PY")
  })
  it("falls back by type when there is no extension", () => {
    expect(attachmentBadgeLabel("", "application/pdf")).toBe("PDF")
    expect(attachmentBadgeLabel("noext", "text/plain")).toBe("FILE")
  })
})

describe("decodeTextDataUrl", () => {
  const url = (s: string) => `data:text/plain;base64,${btoa(s)}`
  it("decodes the full text from a base64 data URL", () => {
    const long = "line\n".repeat(500)
    expect(decodeTextDataUrl(url(long))).toBe(long)
  })
  it("returns empty string for a data URL with no payload", () => {
    expect(decodeTextDataUrl("data:text/plain;base64,")).toBe("")
  })
  it("returns empty string for a malformed data URL", () => {
    expect(decodeTextDataUrl("not a data url")).toBe("")
  })
  it("round-trips multibyte UTF-8", () => {
    const emoji = "Hello 🌍 world — café"
    const bytes = new TextEncoder().encode(emoji)
    const b64 = btoa(String.fromCharCode(...bytes))
    expect(decodeTextDataUrl(`data:text/plain;base64,${b64}`)).toBe(emoji)
  })
  it("returns empty string when the base64 payload is invalid", () => {
    expect(decodeTextDataUrl("data:text/plain;base64,!!!")).toBe("")
  })
})
