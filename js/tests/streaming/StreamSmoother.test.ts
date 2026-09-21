import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { StreamSmoother } from "../../src/streaming/StreamSmoother"

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe("StreamSmoother", () => {
  it("emits nothing before a tick elapses", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push("hello world", null)

    expect(onEmit).not.toHaveBeenCalled()
  })

  it("flush() emits everything immediately without waiting for a tick", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push("hello world", null)
    smoother.flush()

    expect(onEmit).toHaveBeenCalledWith("hello world", null, true)
    // No pending timer left running after a flush.
    expect(vi.getTimerCount()).toBe(0)
  })

  it("dispose() discards buffered text without emitting", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push("hello world", null)
    smoother.dispose()
    vi.advanceTimersByTime(10_000)

    expect(onEmit).not.toHaveBeenCalled()
    expect(vi.getTimerCount()).toBe(0)
  })

  it("never merges two separate pushes, even with identical metadata", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<string>({ onEmit })

    smoother.push("A", "meta")
    smoother.push("B", "meta")
    smoother.flush()

    expect(onEmit).toHaveBeenNthCalledWith(1, "A", "meta", true)
    expect(onEmit).toHaveBeenNthCalledWith(2, "B", "meta", true)
  })

  it("keeps each push's own metadata distinct through pacing", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<{ contentType: string }>({ onEmit })

    smoother.push("thinking text", { contentType: "thinking" })
    smoother.push("regular text", { contentType: "markdown" })
    smoother.flush()

    const calls = onEmit.mock.calls
    expect(calls.some(([, meta]) => meta.contentType === "thinking")).toBe(
      true,
    )
    expect(calls.some(([, meta]) => meta.contentType === "markdown")).toBe(
      true,
    )
    // No emitted slice's text spans both pushes.
    for (const [text] of calls) {
      expect("thinking text".includes(text) || "regular text".includes(text)).toBe(
        true,
      )
    }
  })
})
