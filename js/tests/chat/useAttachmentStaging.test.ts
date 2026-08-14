import { describe, it, expect, vi } from "vitest"
import { renderHook, act } from "@testing-library/react"

vi.mock("../../src/chat/attachments", async (orig) => {
  const actual = await orig<typeof import("../../src/chat/attachments")>()
  return {
    ...actual,
    processFile: vi.fn(async (file: File) => ({
      file: {
        id: `att-${file.name}`,
        type: file.type,
        family: actual.attachmentFamily(file.type) ?? "document",
        dataUrl: `data:${file.type};base64,FAKE`,
        name: file.name,
        // Encode the intended size/flags in the filename so each mock call
        // can behave differently without a shared mutable counter.
        size: file.name.includes("big") ? 1000 : 10,
      },
      wasDownscaled: file.name.includes("downscaled"),
      wasConverted: file.name.includes("gif"),
    })),
  }
})

import { useAttachmentStaging } from "../../src/chat/useAttachmentStaging"

function file(name: string, type = "image/png"): File {
  return new File(["x"], name, { type })
}

describe("useAttachmentStaging", () => {
  it("clears stale notices when applyPayloads replaces the tray (mode: set)", async () => {
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png", "image/gif"],
        maxUploadSize: 25,
        enableUpload: true,
        focusEditor: vi.fn(),
      }),
    )

    // One file blows the size budget (sizeNotice), one was downscaled
    // (downscaleNotice), one was GIF-converted (gifConvertedNotice) -- all
    // three notices should be live at once.
    await act(async () => {
      await result.current.addFiles([
        file("big.png"),
        file("downscaled.png"),
        file("animated.gif"),
      ])
    })

    expect(result.current.sizeNotice).toBe(true)
    expect(result.current.downscaleNotice).toBe(true)
    expect(result.current.gifConvertedNotice).toBe(true)

    // Simulate ChatMessage re-opening edit mode on a message with no
    // attachments: applyPayloads("set") replaces the staged tray, and must
    // not leave the previous session's notices behind.
    act(() => {
      result.current.applyPayloads([], "set")
    })

    expect(result.current.attachments).toEqual([])
    expect(result.current.sizeNotice).toBe(false)
    expect(result.current.downscaleNotice).toBe(false)
    expect(result.current.gifConvertedNotice).toBe(false)
  })

  it("keeps notices intact when applyPayloads appends", async () => {
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png"],
        maxUploadSize: 25,
        enableUpload: true,
        focusEditor: vi.fn(),
      }),
    )

    await act(async () => {
      await result.current.addFiles([file("downscaled.png")])
    })
    expect(result.current.downscaleNotice).toBe(true)

    act(() => {
      result.current.applyPayloads(
        [
          {
            mime: "image/png",
            data_url: "data:image/png;base64,X",
            name: "extra.png",
            size: 5,
          },
        ],
        "append",
      )
    })

    expect(result.current.attachments).toHaveLength(2)
    // Appending doesn't invalidate the earlier downscale, so the notice
    // legitimately stays -- only "set" (a full replace) should reset it.
    expect(result.current.downscaleNotice).toBe(true)
  })
})
