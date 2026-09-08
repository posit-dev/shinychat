import { describe, it, expect, vi } from "vitest"
import { act, renderHook } from "@testing-library/react"
import {
  FADE_DURATION_MS,
  useFadingText,
  useFadingValue,
} from "../../src/chat/useFadingText"

describe("useFadingValue", () => {
  it("holds the swap deadline across re-renders that keep the same key", () => {
    // `value` is a fresh object every render (callers build it inline), so the
    // effect re-runs constantly mid-fade. Those re-runs must not restart the
    // timer, or a busy stretch of renders holds the text invisible long past
    // the fade duration.
    vi.useFakeTimers()
    try {
      const { result, rerender } = renderHook(
        ({ text }) => useFadingValue({ text }, text),
        { initialProps: { text: "Inspecting schema" } },
      )
      rerender({ text: "Inspected schema" })
      expect(result.current.fading).toBe(true)

      act(() => {
        vi.advanceTimersByTime(FADE_DURATION_MS / 2)
      })
      rerender({ text: "Inspected schema" })
      act(() => {
        vi.advanceTimersByTime(FADE_DURATION_MS / 2)
      })

      expect(result.current.fading).toBe(false)
      expect(result.current.visible).toEqual({ text: "Inspected schema" })
    } finally {
      vi.useRealTimers()
    }
  })

  it("ends the fade when the key reverts to the visible one mid-transition", () => {
    // A group of same-tool calls can walk its title through the calls still
    // resolving and land back on the value already on screen (see
    // ToolGroup.test.tsx). The visible text is already the target, so the
    // fade-out must end — not sit at opacity 0 waiting for a timer that was
    // cleared and never re-armed.
    vi.useFakeTimers()
    try {
      const { result, rerender } = renderHook(
        ({ text }) => useFadingText(text),
        { initialProps: { text: "Learned about posit::conf info" } },
      )
      rerender({ text: "Learned about hotel blocks" })
      expect(result.current.fading).toBe(true)

      rerender({ text: "Learned about posit::conf info" })
      act(() => {
        vi.advanceTimersByTime(FADE_DURATION_MS * 2)
      })

      expect(result.current.fading).toBe(false)
      expect(result.current.visible).toBe("Learned about posit::conf info")
    } finally {
      vi.useRealTimers()
    }
  })
})
