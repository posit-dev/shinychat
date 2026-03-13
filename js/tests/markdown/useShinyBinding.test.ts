import { renderHook, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { useShinyBinding } from "../../src/markdown/useShinyBinding"
import type { ContentType, ShinyLifecycle } from "../../src/transport/types"
import { createMockShinyLifecycle } from "../helpers/mocks"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createRef(el: HTMLElement): React.RefObject<HTMLElement | null> {
  return { current: el }
}

// ---------------------------------------------------------------------------
// Basic lifecycle
// ---------------------------------------------------------------------------

describe("useShinyBinding - basic lifecycle", () => {
  let el: HTMLElement
  let shiny: ShinyLifecycle

  beforeEach(() => {
    el = document.createElement("div")
    shiny = createMockShinyLifecycle()
  })

  it("calls bindAll on mount (non-streaming, non-text content)", () => {
    const ref = createRef(el)
    renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "hello",
        streaming: false,
        contentType: "markdown",
      }),
    )

    expect(shiny.bindAll).toHaveBeenCalledWith(el)
    expect(shiny.bindAll).toHaveBeenCalledTimes(1)
  })

  it("calls unbindAll on unmount", () => {
    const ref = createRef(el)
    const { unmount } = renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "hello",
        streaming: false,
        contentType: "markdown",
      }),
    )

    unmount()

    expect(shiny.unbindAll).toHaveBeenCalledWith(el)
  })

  it("calls unbindAll then bindAll when content changes (not streaming)", () => {
    const ref = createRef(el)
    const { rerender } = renderHook(
      (props: { content: string }) =>
        useShinyBinding(ref, shiny, {
          content: props.content,
          streaming: false,
          contentType: "markdown",
        }),
      { initialProps: { content: "hello" } },
    )

    expect(shiny.bindAll).toHaveBeenCalledTimes(1)

    act(() => {
      rerender({ content: "hello world" })
    })

    // Old effect cleanup: unbindAll; new effect: bindAll
    expect(shiny.unbindAll).toHaveBeenCalledWith(el)
    expect(shiny.bindAll).toHaveBeenCalledTimes(2)
  })
})

// ---------------------------------------------------------------------------
// Streaming behavior (THE BUG FIX)
// ---------------------------------------------------------------------------

describe("useShinyBinding - streaming behavior", () => {
  let el: HTMLElement
  let shiny: ShinyLifecycle

  beforeEach(() => {
    vi.useFakeTimers()
    el = document.createElement("div")
    shiny = createMockShinyLifecycle()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("calls bindAll during streaming (after throttle delay)", () => {
    const ref = createRef(el)
    renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "chunk1",
        streaming: true,
        contentType: "markdown",
      }),
    )

    expect(shiny.bindAll).not.toHaveBeenCalled()

    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(shiny.bindAll).toHaveBeenCalledWith(el)
    expect(shiny.bindAll).toHaveBeenCalledTimes(1)
  })

  it("does NOT call unbindAll between streaming chunks (bug fix)", () => {
    const ref = createRef(el)
    const { rerender } = renderHook(
      (props: { content: string }) =>
        useShinyBinding(ref, shiny, {
          content: props.content,
          streaming: true,
          contentType: "markdown",
        }),
      { initialProps: { content: "chunk1" } },
    )

    act(() => {
      rerender({ content: "chunk1 chunk2" })
    })
    act(() => {
      rerender({ content: "chunk1 chunk2 chunk3" })
    })
    act(() => {
      rerender({ content: "chunk1 chunk2 chunk3 chunk4" })
    })

    // The key assertion: unbindAll must NOT have been called during streaming
    expect(shiny.unbindAll).not.toHaveBeenCalled()
  })

  it("calls unbindAll once when component unmounts mid-stream", () => {
    const ref = createRef(el)
    const { unmount } = renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "partial stream",
        streaming: true,
        contentType: "markdown",
      }),
    )

    // Unmount before streaming ends
    unmount()

    expect(shiny.unbindAll).toHaveBeenCalledWith(el)
    expect(shiny.unbindAll).toHaveBeenCalledTimes(1)
  })

  it("calls bindAll when streaming ends (streaming: true → false)", () => {
    const ref = createRef(el)
    const { rerender } = renderHook(
      (props: { streaming: boolean }) =>
        useShinyBinding(ref, shiny, {
          content: "final content",
          streaming: props.streaming,
          contentType: "markdown",
        }),
      { initialProps: { streaming: true } },
    )

    // Advance timers to fire the pending throttled bindAll from streaming
    act(() => {
      vi.advanceTimersByTime(200)
    })

    const bindCallsDuringStreaming = (shiny.bindAll as ReturnType<typeof vi.fn>)
      .mock.calls.length

    act(() => {
      rerender({ streaming: false })
    })

    // bindAll should have been called again now that streaming ended
    expect(shiny.bindAll).toHaveBeenCalledTimes(bindCallsDuringStreaming + 1)
    expect(shiny.bindAll).toHaveBeenCalledWith(el)
  })
})

// ---------------------------------------------------------------------------
// Edge cases
// ---------------------------------------------------------------------------

describe("useShinyBinding - edge cases", () => {
  let shiny: ShinyLifecycle

  beforeEach(() => {
    shiny = createMockShinyLifecycle()
  })

  it("does nothing when ref is null", () => {
    const ref: React.RefObject<HTMLElement | null> = { current: null }
    const { unmount } = renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "hello",
        streaming: false,
        contentType: "markdown",
      }),
    )

    expect(shiny.bindAll).not.toHaveBeenCalled()

    unmount()

    expect(shiny.unbindAll).not.toHaveBeenCalled()
  })

  it("does nothing when contentType is 'text'", () => {
    const el = document.createElement("div")
    const ref = createRef(el)
    const { unmount } = renderHook(() =>
      useShinyBinding(ref, shiny, {
        content: "plain text",
        streaming: false,
        contentType: "text" as ContentType,
      }),
    )

    expect(shiny.bindAll).not.toHaveBeenCalled()

    unmount()

    expect(shiny.unbindAll).not.toHaveBeenCalled()
  })
})

// ---------------------------------------------------------------------------
// Throttle behavior
// ---------------------------------------------------------------------------

describe("useShinyBinding - throttle during streaming", () => {
  let el: HTMLElement
  let shiny: ShinyLifecycle

  beforeEach(() => {
    vi.useFakeTimers()
    el = document.createElement("div")
    shiny = createMockShinyLifecycle()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("bindAll is throttled — not called more than once per 200ms during streaming", () => {
    const ref = createRef(el)
    const { rerender } = renderHook(
      (props: { content: string }) =>
        useShinyBinding(ref, shiny, {
          content: props.content,
          streaming: true,
          contentType: "markdown",
        }),
      { initialProps: { content: "a" } },
    )

    // Simulate rapid chunks arriving within 200ms
    act(() => {
      rerender({ content: "ab" })
    })
    act(() => {
      rerender({ content: "abc" })
    })
    act(() => {
      rerender({ content: "abcd" })
    })

    // No time has passed yet — bindAll should not have fired
    expect(shiny.bindAll).not.toHaveBeenCalled()

    // Advance 200ms — only one bindAll should fire
    act(() => {
      vi.advanceTimersByTime(200)
    })

    expect(shiny.bindAll).toHaveBeenCalledTimes(1)
  })
})
