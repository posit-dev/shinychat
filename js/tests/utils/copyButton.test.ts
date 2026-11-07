import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  copyTextToClipboard,
  createCopyButton,
  flashCopied,
} from "../../src/utils/copyButton"

function mockClipboard(writeText: ReturnType<typeof vi.fn>) {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  })
}

describe("copyTextToClipboard", () => {
  it("uses the async clipboard API when it succeeds", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    mockClipboard(writeText)
    const execCommand = vi.fn()
    document.execCommand = execCommand

    await copyTextToClipboard("x <- 1")

    expect(writeText).toHaveBeenCalledWith("x <- 1")
    expect(execCommand).not.toHaveBeenCalled()
  })

  it("falls back to a textarea + execCommand when writeText fails", async () => {
    // e.g. iframes without clipboard-write permission
    const writeText = vi.fn().mockRejectedValue(new Error("denied"))
    mockClipboard(writeText)
    const execCommand = vi.fn()
    document.execCommand = execCommand

    await copyTextToClipboard("x <- 1")

    expect(execCommand).toHaveBeenCalledWith("copy")
    // The helper textarea is transient.
    expect(document.body.querySelector("textarea")).toBeNull()
  })
})

describe("flashCopied", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it("adds the checked class, then removes it after 2s", () => {
    const button = document.createElement("button")
    flashCopied(button)
    expect(button.classList.contains("code-copy-button-checked")).toBe(true)

    vi.advanceTimersByTime(2000)
    expect(button.classList.contains("code-copy-button-checked")).toBe(false)
  })

  it("cancel prevents the removal (a newer flash owns the button)", () => {
    const button = document.createElement("button")
    const cancel = flashCopied(button)
    cancel()
    vi.advanceTimersByTime(5000)
    expect(button.classList.contains("code-copy-button-checked")).toBe(true)
  })
})

describe("createCopyButton", () => {
  it("builds the standard affordance", () => {
    const button = createCopyButton()
    expect(button.type).toBe("button")
    expect(button.className).toBe("code-copy-button")
    expect(button.title).toBe("Copy to clipboard")
    expect(button.getAttribute("aria-label")).toBe("Copy to clipboard")
    expect(button.querySelector("i.bi")).toBeTruthy()
  })
})
