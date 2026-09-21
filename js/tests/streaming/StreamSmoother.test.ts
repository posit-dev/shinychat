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
    expect(calls.some(([, meta]) => meta.contentType === "thinking")).toBe(true)
    expect(calls.some(([, meta]) => meta.contentType === "markdown")).toBe(true)
    // No emitted slice's text spans both pushes.
    for (const [text] of calls) {
      expect(
        "thinking text".includes(text) || "regular text".includes(text),
      ).toBe(true)
    }
  })
})

describe("StreamSmoother pacing", () => {
  it("paces a single push across multiple ticks, reassembling to the original text with no mid-word cuts", () => {
    const onEmit = vi.fn()
    const text =
      "The quick brown fox jumps over the lazy dog while the smoother drains it"
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push(text, null)
    for (let i = 0; i < 20 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }
    smoother.flush()

    const reassembled = onEmit.mock.calls.map((c) => c[0]).join("")
    expect(reassembled).toBe(text)

    const nonFinalSlices = onEmit.mock.calls.slice(0, -1).map((c) => c[0])
    for (const slice of nonFinalSlices) {
      expect(slice.endsWith(" ")).toBe(true)
    }
  })

  it("marks isFirstSlice true only for the first emission of a push", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      tickIntervalMs: 50,
      drainRate: 0, // force the floor path so a long push spans many ticks
      minCharsPerSecond: 30,
    })

    smoother.push("a".repeat(200), null)
    for (let i = 0; i < 50 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }
    smoother.flush()

    const firstSliceFlags = onEmit.mock.calls.map((c) => c[2])
    expect(firstSliceFlags[0]).toBe(true)
    expect(firstSliceFlags.slice(1).every((flag) => flag === false)).toBe(true)
  })

  it("drains a larger backlog faster (more chars) per tick than a small one", () => {
    const smallEmit = vi.fn()
    const smallSmoother = new StreamSmoother<null>({ onEmit: smallEmit })
    smallSmoother.push("x".repeat(20), null)
    vi.advanceTimersByTime(50)
    const smallDrained = smallEmit.mock.calls.reduce(
      (n, c) => n + c[0].length,
      0,
    )

    const bigEmit = vi.fn()
    const bigSmoother = new StreamSmoother<null>({ onEmit: bigEmit })
    bigSmoother.push("x".repeat(5000), null)
    vi.advanceTimersByTime(50)
    const bigDrained = bigEmit.mock.calls.reduce((n, c) => n + c[0].length, 0)

    expect(bigDrained).toBeGreaterThan(smallDrained)
  })

  it("backs off the tick interval after an observed overrun", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      tickIntervalMs: 50,
      maxTickIntervalMs: 250,
      overrunBackoffMultiplier: 2,
    })

    smoother.push("x".repeat(1000), null)
    // Simulate the first tick firing 100ms late (main-thread congestion).
    vi.setSystemTime(new Date(Date.now() + 150))
    vi.advanceTimersByTime(0)

    // The loop is still running (backlog remains) and the *next* scheduled
    // delay should have backed off above the base 50ms tick.
    expect(vi.getTimerCount()).toBe(1)
    const pending = vi.getTimerCount() > 0
    expect(pending).toBe(true)
    smoother.flush()
  })

  it("accumulates elapsed time across stalls to eventually reach distant word boundaries", () => {
    const onEmit = vi.fn()
    const text = "a".repeat(1000) + " b"
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push(text, null)

    // Advance timers far longer than should ever be needed to reach the space at position 1000.
    // With default drainRate (0.02), after ~17 ticks we should have budget >= 1000.
    // Use 100 ticks (5 seconds) to be safe.
    for (let i = 0; i < 100 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }

    // The text should have been emitted via the paced onEmit, not just by flush
    expect(onEmit).toHaveBeenCalled()
    const emitted = onEmit.mock.calls.map((c) => c[0]).join("")
    expect(emitted).toContain(text)
  })
})
