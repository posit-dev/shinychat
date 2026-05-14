import { renderHook, act } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { useInputHistory } from "../../src/chat/useInputHistory"

describe("useInputHistory", () => {
  describe("recall up", () => {
    it("returns undefined when history is empty", () => {
      const { result } = renderHook(() => useInputHistory([]))
      const value = result.current.recall("up", "")
      expect(value).toBeUndefined()
    })

    it("recalls most recent message first", () => {
      const { result } = renderHook(() =>
        useInputHistory(["first", "second", "third"]),
      )
      const value = result.current.recall("up", "")
      expect(value).toBe("third")
    })

    it("cycles backward through history", () => {
      const { result } = renderHook(() =>
        useInputHistory(["first", "second", "third"]),
      )
      expect(result.current.recall("up", "")).toBe("third")
      expect(result.current.recall("up", "third")).toBe("second")
      expect(result.current.recall("up", "second")).toBe("first")
    })

    it("clamps at oldest message", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      expect(result.current.recall("up", "")).toBe("second")
      expect(result.current.recall("up", "second")).toBe("first")
      expect(result.current.recall("up", "first")).toBe("first")
    })
  })

  describe("recall down", () => {
    it("returns undefined from fresh state", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      const value = result.current.recall("down", "")
      expect(value).toBeUndefined()
    })

    it("cycles forward through history", () => {
      const { result } = renderHook(() =>
        useInputHistory(["first", "second", "third"]),
      )
      result.current.recall("up", "")
      result.current.recall("up", "third")
      result.current.recall("up", "second")
      // Now at "first" (index 0)
      expect(result.current.recall("down", "first")).toBe("second")
      expect(result.current.recall("down", "second")).toBe("third")
    })

    it("returns empty string when moving past most recent", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      result.current.recall("up", "")
      // At "second" (index 1, which is maxIdx)
      expect(result.current.recall("down", "second")).toBe("")
    })

    it("restores draft for blank slot when moving past most recent", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      // Start typing "draft", then press up
      result.current.recall("up", "draft")
      // Now at "second"; press down to return to blank slot
      expect(result.current.recall("down", "second")).toBe("draft")
    })
  })

  describe("draft preservation", () => {
    it("preserves edits when navigating away and back", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      // Go to "second"
      result.current.recall("up", "")
      // Edit it, then go to "first"
      result.current.recall("up", "second-edited")
      // Go back to "second" slot
      expect(result.current.recall("down", "first")).toBe("second-edited")
    })

    it("returns original message when no draft exists", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      result.current.recall("up", "")
      result.current.recall("up", "second")
      // Navigate back to "second" without editing "first"
      expect(result.current.recall("down", "first")).toBe("second")
    })

    it("preserves blank-slot draft across multiple navigations", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      // Type "wip", navigate up twice, then back down twice
      result.current.recall("up", "wip")
      result.current.recall("up", "second")
      result.current.recall("down", "first")
      expect(result.current.recall("down", "second")).toBe("wip")
    })
  })

  describe("reset", () => {
    it("resets index so up recalls most recent again", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      result.current.recall("up", "")
      result.current.recall("up", "second")
      // Now at "first"; reset
      act(() => result.current.reset())
      expect(result.current.recall("up", "")).toBe("second")
    })

    it("clears drafts", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      result.current.recall("up", "")
      result.current.recall("up", "second-edited")
      act(() => result.current.reset())
      // After reset, navigating to "second" should return original
      expect(result.current.recall("up", "")).toBe("second")
    })

    it("down returns undefined after reset", () => {
      const { result } = renderHook(() => useInputHistory(["first", "second"]))
      result.current.recall("up", "")
      act(() => result.current.reset())
      expect(result.current.recall("down", "")).toBeUndefined()
    })
  })

  describe("stale index handling", () => {
    it("clamps stale index when history shrinks", () => {
      const { result, rerender } = renderHook(
        ({ messages }) => useInputHistory(messages),
        { initialProps: { messages: ["first", "second", "third"] } },
      )
      // Navigate to "first" (index 0)
      result.current.recall("up", "")
      result.current.recall("up", "third")
      result.current.recall("up", "second")

      // History shrinks — rerender with fewer messages
      rerender({ messages: ["only"] })

      // Up should recover and return the only message
      expect(result.current.recall("up", "first")).toBe("only")
    })
  })
})
