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

  // These tests decouple "when the fake-timer clock fires the pending
  // setTimeout" from "what Date.now() reports at that moment", by spying on
  // Date.now() directly. That lets us pin an exact, deterministic overrun
  // (the gap between the mocked "now" and the scheduled deadline) without
  // relying on vi.setSystemTime, which does not itself fire due timers.
  it("backs off the next interval proportionally to the observed overrun (tickIntervalMs + multiplier * overrunMs), not multiplicatively", () => {
    const onEmit = vi.fn()
    const setTimeoutSpy = vi.spyOn(global, "setTimeout")
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const smoother = new StreamSmoother<null>({
      onEmit,
      tickIntervalMs: 50,
      maxTickIntervalMs: 250,
      overrunBackoffMultiplier: 2,
    })

    // Scheduled deadline (nextTickAt) is captured as Date.now() + 50 = 1050.
    smoother.push("x".repeat(1000), null)
    // The tick fires 20ms late: Date.now() reports 1070 when tick() runs.
    dateNowSpy.mockReturnValue(1070)
    vi.advanceTimersByTime(50)

    // next interval = tickIntervalMs(50) + overrunBackoffMultiplier(2) * overrun(20) = 90
    const lastCall = setTimeoutSpy.mock.calls.at(-1)
    const scheduledDelay = lastCall?.[1]
    expect(scheduledDelay).toBe(90)

    smoother.flush()
    setTimeoutSpy.mockRestore()
    dateNowSpy.mockRestore()
  })

  it("caps the backed-off interval at maxTickIntervalMs even under a large overrun", () => {
    const onEmit = vi.fn()
    const setTimeoutSpy = vi.spyOn(global, "setTimeout")
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const smoother = new StreamSmoother<null>({
      onEmit,
      tickIntervalMs: 50,
      maxTickIntervalMs: 250,
      overrunBackoffMultiplier: 2,
    })

    // Scheduled deadline is 1050. Fire 200ms late (now = 1250), which would
    // put the raw formula (50 + 2*200 = 450) well above the 250ms cap.
    smoother.push("x".repeat(1000), null)
    dateNowSpy.mockReturnValue(1250)
    vi.advanceTimersByTime(50)

    const lastCall = setTimeoutSpy.mock.calls.at(-1)
    const scheduledDelay = lastCall?.[1]
    expect(scheduledDelay).toBe(250)

    smoother.flush()
    setTimeoutSpy.mockRestore()
    dateNowSpy.mockRestore()
  })

  it("resets the interval back to tickIntervalMs once the queue naturally drains", () => {
    const onEmit = vi.fn()
    const setTimeoutSpy = vi.spyOn(global, "setTimeout")
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(1000)
    const smoother = new StreamSmoother<null>({
      onEmit,
      tickIntervalMs: 50,
      maxTickIntervalMs: 250,
      overrunBackoffMultiplier: 2,
    })

    // A short push that fully drains on the very first tick despite a
    // large overrun: currentIntervalMs should reset to tickIntervalMs
    // rather than staying backed off for the next unrelated burst.
    smoother.push("hi", null)
    dateNowSpy.mockReturnValue(1250)
    vi.advanceTimersByTime(50)

    expect(onEmit).toHaveBeenCalledWith("hi", null, true)
    expect(vi.getTimerCount()).toBe(0)

    // The next push should be scheduled at the base interval, not a
    // leftover backed-off one.
    smoother.push("next burst", null)
    const lastCall = setTimeoutSpy.mock.calls.at(-1)
    expect(lastCall?.[1]).toBe(50)

    smoother.flush()
    setTimeoutSpy.mockRestore()
    dateNowSpy.mockRestore()
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
