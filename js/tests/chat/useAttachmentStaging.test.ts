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
import { processFile } from "../../src/chat/attachments"

function file(name: string, type = "image/png"): File {
  return new File(["x"], name, { type })
}

describe("useAttachmentStaging", () => {
  it("retains an upload started before an unrelated transition locks the editor", async () => {
    let editable = true
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png"],
        maxUploadSize: null,
        enableUpload: true,
        focusEditor: vi.fn(),
        canMutate: () => editable,
      }),
    )
    await act(async () => {
      const work = result.current.addFiles([file("draft.png")])
      editable = false
      await work
    })
    expect(result.current.getPayloads()).toEqual([
      {
        mime: "image/png",
        data_url: "data:image/png;base64,FAKE",
        name: "draft.png",
        size: 10,
      },
    ])
    expect(result.current.isProcessing()).toBe(false)
  })

  it("holds submission through a batched failed conversion until the commit", async () => {
    vi.mocked(processFile).mockRejectedValueOnce(new Error("read failed"))
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png"],
        maxUploadSize: null,
        enableUpload: true,
        focusEditor: vi.fn(),
      }),
    )
    await act(async () => {
      const work = result.current.addFiles([file("broken.png")])
      expect(result.current.isProcessing()).toBe(true)
      await work
      expect(result.current.isProcessing()).toBe(true)
    })
    expect(result.current.processing).toBe(false)
    expect(result.current.isProcessing()).toBe(false)
    expect(result.current.getPayloads()).toEqual([])
  })

  it("publishes every concurrent result before allowing submission", async () => {
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png"],
        maxUploadSize: null,
        enableUpload: true,
        focusEditor: vi.fn(),
      }),
    )
    await act(async () => {
      const first = result.current.addFiles([file("first.png")])
      const second = result.current.addFiles([file("second.png")])
      expect(result.current.isProcessing()).toBe(true)
      await Promise.all([first, second])
      expect(result.current.isProcessing()).toBe(true)
    })
    expect(result.current.processing).toBe(false)
    expect(result.current.isProcessing()).toBe(false)
    expect(result.current.getPayloads()).toEqual([
      {
        mime: "image/png",
        data_url: "data:image/png;base64,FAKE",
        name: "first.png",
        size: 10,
      },
      {
        mime: "image/png",
        data_url: "data:image/png;base64,FAKE",
        name: "second.png",
        size: 10,
      },
    ])
  })

  it("applies the size limit across concurrent additions", async () => {
    const { result } = renderHook(() =>
      useAttachmentStaging({
        uploadAccept: ["image/png"],
        maxUploadSize: 15,
        enableUpload: true,
        focusEditor: vi.fn(),
      }),
    )
    await act(async () => {
      await Promise.all([
        result.current.addFiles([file("first.png")]),
        result.current.addFiles([file("second.png")]),
      ])
    })
    expect(result.current.getPayloads()).toEqual([
      {
        mime: "image/png",
        data_url: "data:image/png;base64,FAKE",
        name: "first.png",
        size: 10,
      },
    ])
    expect(result.current.sizeNotice).toBe(true)
    expect(result.current.isProcessing()).toBe(false)
  })

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
