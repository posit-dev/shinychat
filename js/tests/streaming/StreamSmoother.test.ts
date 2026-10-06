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

  it("never merges two separate pushes by default, even with identical metadata", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<string>({ onEmit })

    smoother.push("A", "meta")
    smoother.push("B", "meta")
    smoother.flush()

    expect(onEmit).toHaveBeenNthCalledWith(1, "A", "meta", true)
    expect(onEmit).toHaveBeenNthCalledWith(2, "B", "meta", true)
  })

  it("merges consecutive pushes into one entry when canMerge allows", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<string>({
      onEmit,
      canMerge: (a, b) => a === b,
    })

    smoother.push("A", "meta")
    smoother.push("B", "meta")
    smoother.push("C", "other")
    smoother.flush()

    expect(onEmit.mock.calls).toEqual([
      ["AB", "meta", true],
      ["C", "other", true],
    ])
  })

  it("merges into a partially emitted tail without re-flagging isFirstSlice", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      canMerge: () => true,
      drainRate: 0,
      minCharsPerSecond: 60, // 3 chars per 50ms tick
    })

    smoother.push("abcdef", null)
    vi.advanceTimersByTime(50)
    smoother.push("ghi", null)
    smoother.flush()

    expect(onEmit.mock.calls).toEqual([
      ["abc", null, true],
      ["defghi", null, false],
    ])
  })

  it("lets a paced slice span pushes once they are merged", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      canMerge: () => true,
      drainRate: 0,
      minCharsPerSecond: 60, // 3 chars per 50ms tick
    })

    smoother.push("ab", null)
    smoother.push("cd", null)
    vi.advanceTimersByTime(50)

    expect(onEmit).toHaveBeenCalledTimes(1)
    expect(onEmit).toHaveBeenCalledWith("abc", null, true)
    smoother.dispose()
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
  it("paces a single push across multiple ticks at character granularity", () => {
    const onEmit = vi.fn()
    const text =
      "The quick brown fox jumps over the lazy dog while the smoother drains it"
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push(text, null)
    for (let i = 0; i < 20 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }
    smoother.flush()

    const slices = onEmit.mock.calls.map((c) => c[0] as string)
    expect(slices.join("")).toBe(text)
    expect(slices.length).toBeGreaterThan(5)
    // Cuts are not snapped to whitespace: some slice ends mid-word.
    expect(slices.slice(0, -1).some((s) => /\S$/.test(s))).toBe(true)
    // Paced slices (excluding the final flush) stay small.
    const paced = slices.slice(0, -1)
    expect(Math.max(...paced.map((s) => s.length))).toBeLessThan(10)
  })

  it("carries a fractional character budget across ticks", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      drainRate: 0,
      minCharsPerSecond: 10, // 0.5 chars per 50ms tick
    })

    smoother.push("abcd", null)
    const emittedAfter = (ticks: number) => {
      vi.advanceTimersByTime(50 * ticks)
      return onEmit.mock.calls.map((c) => c[0]).join("")
    }

    expect(emittedAfter(1)).toBe("")
    expect(emittedAfter(1)).toBe("a")
    expect(emittedAfter(2)).toBe("ab")
    expect(emittedAfter(4)).toBe("abcd")
    expect(vi.getTimerCount()).toBe(0)
  })

  it("never splits a UTF-16 surrogate pair", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      drainRate: 0,
      minCharsPerSecond: 20, // 1 char per 50ms tick
    })

    const text = "a😀b😀c"
    smoother.push(text, null)
    for (let i = 0; i < 20 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }

    const slices = onEmit.mock.calls.map((c) => c[0] as string)
    expect(slices.join("")).toBe(text)
    for (const slice of slices) {
      // No lone high or low surrogate in any emitted slice.
      expect(slice).not.toMatch(
        /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/,
      )
    }
  })

  it("never splits a run of markdown marker characters", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({
      onEmit,
      drainRate: 0,
      minCharsPerSecond: 20, // 1 char per 50ms tick
    })

    const text = "x\n```py\n**b** ~~~\n```"
    smoother.push(text, null)
    for (let i = 0; i < 50 && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }

    const slices = onEmit.mock.calls.map((c) => c[0] as string)
    expect(slices.join("")).toBe(text)
    for (let i = 1; i < slices.length; i++) {
      const prev = slices[i - 1]!.at(-1)!
      const next = slices[i]![0]!
      expect(prev === next && "`~*_".includes(next)).toBe(false)
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

    // Loop start (lastTickAt) is captured as Date.now() = 1000; deadline is 1050.
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

  it("emits on every tick for long unbroken text instead of stalling", () => {
    const onEmit = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit })

    smoother.push("a".repeat(1000) + " b", null)
    for (let i = 0; i < 10; i++) {
      const before = onEmit.mock.calls.length
      vi.advanceTimersByTime(50)
      expect(onEmit.mock.calls.length).toBeGreaterThan(before)
    }
    smoother.dispose()
  })
})

describe("StreamSmoother finish()", () => {
  const drainTicks = (max = 100) => {
    for (let i = 0; i < max && vi.getTimerCount() > 0; i++) {
      vi.advanceTimersByTime(50)
    }
  }

  it("calls onDone synchronously when nothing is buffered", () => {
    const onDone = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit: vi.fn() })

    smoother.finish(onDone)

    expect(onDone).toHaveBeenCalledTimes(1)
    expect(smoother.finishing).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("drains the tail over several ticks within finishDurationMs, then calls onDone", () => {
    const events: string[] = []
    const smoother = new StreamSmoother<null>({
      onEmit: (text) => events.push(text),
      finishDurationMs: 400,
    })
    const text = "x".repeat(300)

    smoother.push(text, null)
    smoother.finish(() => events.push("DONE"))
    expect(smoother.finishing).toBe(true)
    expect(events).toEqual([])

    // Not dumped in one go...
    vi.advanceTimersByTime(50)
    expect(events.join("").length).toBeGreaterThan(0)
    expect(events.join("").length).toBeLessThan(text.length)

    // ...but done within the window (plus one tick of slack).
    vi.advanceTimersByTime(400)
    expect(events.at(-1)).toBe("DONE")
    expect(events.slice(0, -1).join("")).toBe(text)
    expect(smoother.finishing).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("drains faster than normal pacing", () => {
    const run = (finish: boolean) => {
      const emitted: string[] = []
      const smoother = new StreamSmoother<null>({
        onEmit: (t) => emitted.push(t),
      })
      smoother.push("x".repeat(300), null)
      if (finish) smoother.finish(() => {})
      vi.advanceTimersByTime(200)
      smoother.dispose()
      return emitted.join("").length
    }
    expect(run(true)).toBeGreaterThan(run(false))
  })

  it("flush() during a finish emits the rest and calls onDone once", () => {
    const events: string[] = []
    const smoother = new StreamSmoother<null>({
      onEmit: (text) => events.push(text),
    })

    smoother.push("hello world", null)
    smoother.finish(() => events.push("DONE"))
    smoother.flush()
    drainTicks()

    expect(events).toEqual(["hello world", "DONE"])
    expect(smoother.finishing).toBe(false)
  })

  it("dispose() during a finish cancels onDone", () => {
    const onDone = vi.fn()
    const smoother = new StreamSmoother<null>({ onEmit: vi.fn() })

    smoother.push("hello world", null)
    smoother.finish(onDone)
    smoother.dispose()
    drainTicks()

    expect(onDone).not.toHaveBeenCalled()
    expect(smoother.finishing).toBe(false)
  })
})
