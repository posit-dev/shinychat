import { renderHook, act } from "@testing-library/react"
import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  useAutoScroll,
  findScrollableParent,
} from "../src/markdown/useAutoScroll"

/**
 * Creates a mock DOM element with configurable scroll dimensions.
 */
function createMockScrollContainer(
  options: {
    scrollTop?: number
    scrollHeight?: number
    clientHeight?: number
  } = {},
): HTMLDivElement {
  const element = document.createElement("div")

  let _scrollTop = options.scrollTop ?? 0
  const _scrollHeight = options.scrollHeight ?? 1000
  const _clientHeight = options.clientHeight ?? 500

  Object.defineProperty(element, "scrollTop", {
    get: () => _scrollTop,
    set: (value: number) => {
      _scrollTop = value
    },
    configurable: true,
  })

  Object.defineProperty(element, "scrollHeight", {
    get: () => _scrollHeight,
    configurable: true,
  })

  Object.defineProperty(element, "clientHeight", {
    get: () => _clientHeight,
    configurable: true,
  })

  element.scrollTo = vi.fn((...args: unknown[]) => {
    const opts = (typeof args[0] === "object" ? args[0] : {}) as ScrollToOptions
    if (opts.top !== undefined) {
      _scrollTop = opts.top
    }
  })

  return element
}

/**
 * Simulates a scroll event by overriding scrollTop and dispatching a scroll event.
 */
function simulateScroll(element: HTMLElement, newScrollTop: number): void {
  Object.defineProperty(element, "scrollTop", {
    get: () => newScrollTop,
    configurable: true,
  })
  element.dispatchEvent(new Event("scroll"))
}

describe("useAutoScroll", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe("initial state", () => {
    it("starts with stickToBottom true", () => {
      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      expect(result.current.stickToBottom).toBe(true)
    })

    it("provides a containerRef callback", () => {
      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      expect(typeof result.current.containerRef).toBe("function")
    })

    it("provides a scrollToBottom function", () => {
      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      expect(typeof result.current.scrollToBottom).toBe("function")
    })
  })

  describe("callback ref", () => {
    it("attaches scroll listener with passive option when element is provided", () => {
      const element = createMockScrollContainer()
      const addEventListenerSpy = vi.spyOn(element, "addEventListener")

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      expect(addEventListenerSpy).toHaveBeenCalledWith(
        "scroll",
        expect.any(Function),
        { passive: true },
      )
    })

    it("removes scroll listener when element changes", () => {
      const element1 = createMockScrollContainer()
      const element2 = createMockScrollContainer()
      const removeSpy = vi.spyOn(element1, "removeEventListener")

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element1)
      })

      act(() => {
        result.current.containerRef(element2)
      })

      expect(removeSpy).toHaveBeenCalledWith("scroll", expect.any(Function))
    })

    it("handles null element without throwing", () => {
      const element = createMockScrollContainer()

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      act(() => {
        result.current.containerRef(null)
      })

      expect(result.current.stickToBottom).toBe(true)
    })
  })

  describe("scroll detection", () => {
    it("disengages stickToBottom when user scrolls up", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      expect(result.current.stickToBottom).toBe(true)

      act(() => {
        simulateScroll(element, 300)
      })

      expect(result.current.stickToBottom).toBe(false)
    })

    it("re-engages stickToBottom when user scrolls back to bottom", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Scroll back to bottom
      act(() => {
        simulateScroll(element, 500)
      })
      expect(result.current.stickToBottom).toBe(true)
    })

    it("uses custom bottomTolerance", () => {
      const element = createMockScrollContainer({
        scrollTop: 470,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
          bottomTolerance: 50,
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Scroll to 30px from bottom — within 50px tolerance
      act(() => {
        simulateScroll(element, 470)
      })
      expect(result.current.stickToBottom).toBe(true)
    })

    it("defaults to 10px tolerance", () => {
      const element = createMockScrollContainer({
        scrollTop: 485,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Scroll to 15px from bottom — outside default 10px tolerance
      act(() => {
        simulateScroll(element, 485)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Scroll to 5px from bottom — within tolerance
      act(() => {
        simulateScroll(element, 495)
      })
      expect(result.current.stickToBottom).toBe(true)
    })
  })

  describe("auto-scroll during streaming", () => {
    it("scrolls to bottom when streaming and stickToBottom is true", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      rerender({ streaming: true, contentDependency: ["new message"] })

      expect(element.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      })
    })

    it("does not scroll when not streaming (default scrollOnContentChange=false)", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      rerender({ streaming: false, contentDependency: ["new message"] })

      expect(element.scrollTo).not.toHaveBeenCalled()
    })

    it("does not scroll when stickToBottom is false", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Start streaming
      rerender({ streaming: true, contentDependency: ["new message"] })

      expect(element.scrollTo).not.toHaveBeenCalled()
    })

    it("handles rapid content updates during streaming", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
          }),
        {
          initialProps: {
            streaming: true,
            contentDependency: [1] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      for (let i = 2; i <= 5; i++) {
        rerender({ streaming: true, contentDependency: [i] })
      }

      expect(element.scrollTo).toHaveBeenCalled()
    })
  })

  describe("scrollToBottom", () => {
    it("scrolls to bottom when called", () => {
      const element = createMockScrollContainer({
        scrollTop: 300,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Disengage first
      act(() => {
        simulateScroll(element, 200)
      })
      expect(result.current.stickToBottom).toBe(false)

      act(() => {
        result.current.scrollToBottom()
      })

      expect(element.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      })
    })

    it("re-engages stickToBottom when called", () => {
      const element = createMockScrollContainer({
        scrollTop: 300,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      act(() => {
        simulateScroll(element, 200)
      })
      expect(result.current.stickToBottom).toBe(false)

      act(() => {
        result.current.scrollToBottom()
      })

      expect(result.current.stickToBottom).toBe(true)
    })

    it("does nothing when no container is attached", () => {
      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      // Should not throw
      act(() => {
        result.current.scrollToBottom()
      })

      expect(result.current.stickToBottom).toBe(true)
    })
  })

  describe("scrollOnContentChange", () => {
    it("scrolls on non-streaming content change when scrollOnContentChange is true and stickToBottom is true", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
            scrollOnContentChange: true,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      rerender({ streaming: false, contentDependency: ["new message"] })

      expect(element.scrollTo).toHaveBeenCalled()
    })

    it("does not scroll when stickToBottom is false even with scrollOnContentChange", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
            scrollOnContentChange: true,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage stickToBottom
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      rerender({ streaming: false, contentDependency: ["new message"] })

      expect(element.scrollTo).not.toHaveBeenCalled()
    })

    it("uses smooth behavior for non-streaming scrolls", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
            scrollOnContentChange: true,
          }),
        {
          initialProps: {
            streaming: false,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      rerender({ streaming: false, contentDependency: ["new message"] })

      expect(element.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      })
    })

    it("uses smooth behavior for streaming scrolls", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
            scrollOnContentChange: true,
          }),
        {
          initialProps: {
            streaming: true,
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      rerender({ streaming: true, contentDependency: ["new message"] })

      expect(element.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      })
    })
  })

  describe("engageStickToBottom", () => {
    it("sets stickToBottom to true without calling scrollTo", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage stickToBottom
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      act(() => {
        result.current.engageStickToBottom()
      })

      expect(result.current.stickToBottom).toBe(true)
      expect(element.scrollTo).not.toHaveBeenCalled()
    })

    it("is a no-op when already stuck to bottom", () => {
      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      // stickToBottom starts true
      expect(result.current.stickToBottom).toBe(true)

      act(() => {
        result.current.engageStickToBottom()
      })

      expect(result.current.stickToBottom).toBe(true)
    })

    it("triggers scroll on next content change after re-engaging (with scrollOnContentChange)", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: false,
            contentDependency: props.contentDependency,
            scrollOnContentChange: true,
          }),
        {
          initialProps: {
            contentDependency: [] as unknown[],
          },
        },
      )

      act(() => {
        result.current.containerRef(element)
      })

      // Scroll up to disengage stickToBottom
      act(() => {
        simulateScroll(element, 300)
      })
      expect(result.current.stickToBottom).toBe(false)

      // Re-engage without an explicit scroll call
      act(() => {
        result.current.engageStickToBottom()
      })
      expect(result.current.stickToBottom).toBe(true)

      // Clear any scrollTo calls that may have fired when stickToBottom
      // flipped back to true (the effect re-runs on state change).
      vi.clearAllMocks()

      // New content arrives — the effect should fire again and scroll
      rerender({ contentDependency: ["new message"] })

      expect(element.scrollTo).toHaveBeenCalledWith({
        top: 1000,
        behavior: "smooth",
      })
    })
  })

  describe("edge cases", () => {
    it("handles container with no scroll (content fits)", () => {
      const element = createMockScrollContainer({
        scrollTop: 0,
        scrollHeight: 500,
        clientHeight: 500,
      })

      const { result } = renderHook(() =>
        useAutoScroll({
          streaming: false,
          contentDependency: [],
        }),
      )

      act(() => {
        result.current.containerRef(element)
      })

      expect(result.current.stickToBottom).toBe(true)

      act(() => {
        simulateScroll(element, 0)
      })

      expect(result.current.stickToBottom).toBe(true)
    })

    it("does not re-register listener when content changes during streaming", () => {
      const element = createMockScrollContainer({
        scrollTop: 500,
        scrollHeight: 1000,
        clientHeight: 500,
      })
      const addSpy = vi.spyOn(element, "addEventListener")
      const removeSpy = vi.spyOn(element, "removeEventListener")

      const { result, rerender } = renderHook(
        (props) =>
          useAutoScroll({
            streaming: props.streaming,
            contentDependency: props.contentDependency,
          }),
        { initialProps: { streaming: true, contentDependency: "a" as string } },
      )

      act(() => {
        result.current.containerRef(element)
      })

      const addCount = addSpy.mock.calls.length
      const removeCount = removeSpy.mock.calls.length

      // Simulate several content updates
      rerender({ streaming: true, contentDependency: "ab" })
      rerender({ streaming: true, contentDependency: "abc" })
      rerender({ streaming: true, contentDependency: "abcd" })

      // Listener should NOT have been re-registered
      expect(addSpy.mock.calls.length).toBe(addCount)
      expect(removeSpy.mock.calls.length).toBe(removeCount)
    })
  })
})

describe("findScrollableParent", () => {
  it("finds the nearest scrollable ancestor", () => {
    const grandparent = document.createElement("div")
    Object.defineProperty(grandparent.style, "overflowY", { value: "auto" })

    const parent = document.createElement("div")
    const child = document.createElement("div")

    grandparent.appendChild(parent)
    parent.appendChild(child)

    Object.defineProperty(grandparent, "scrollHeight", {
      configurable: true,
      get: () => 600,
    })
    Object.defineProperty(grandparent, "clientHeight", {
      configurable: true,
      get: () => 300,
    })

    // jsdom returns "" for getComputedStyle by default, so we need to
    // make the grandparent actually scrollable
    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === grandparent) {
        return { ...style, overflowY: "auto" } as CSSStyleDeclaration
      }
      return style
    })

    expect(findScrollableParent(child)).toBe(grandparent)

    vi.restoreAllMocks()
  })

  it("returns null when no scrollable ancestor exists", () => {
    const parent = document.createElement("div")
    const child = document.createElement("div")
    parent.appendChild(child)

    expect(findScrollableParent(child)).toBeNull()
  })

  it("stops at the specified tag", () => {
    const outer = document.createElement("div")
    Object.defineProperty(outer.style, "overflowY", { value: "auto" })

    const boundary = document.createElement("shiny-chat-container")
    const child = document.createElement("div")

    outer.appendChild(boundary)
    boundary.appendChild(child)

    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === outer) {
        return { ...style, overflowY: "auto" } as CSSStyleDeclaration
      }
      return style
    })

    // Should not find the outer element because the boundary tag stops the walk
    expect(findScrollableParent(child, "shiny-chat-container")).toBeNull()

    vi.restoreAllMocks()
  })

  it("recognizes overflow-y: scroll when content overflows", () => {
    const parent = document.createElement("div")
    const child = document.createElement("div")
    parent.appendChild(child)

    Object.defineProperty(parent, "scrollHeight", {
      configurable: true,
      get: () => 600,
    })
    Object.defineProperty(parent, "clientHeight", {
      configurable: true,
      get: () => 300,
    })

    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === parent) {
        return { ...style, overflowY: "scroll" } as CSSStyleDeclaration
      }
      return style
    })

    expect(findScrollableParent(child)).toBe(parent)

    vi.restoreAllMocks()
  })

  it("skips overflow-y:auto ancestors that do not actually scroll", () => {
    const outer = document.createElement("div")
    const inner = document.createElement("div")
    const child = document.createElement("div")

    outer.appendChild(inner)
    inner.appendChild(child)

    Object.defineProperty(outer, "scrollHeight", {
      configurable: true,
      get: () => 600,
    })
    Object.defineProperty(outer, "clientHeight", {
      configurable: true,
      get: () => 300,
    })
    Object.defineProperty(inner, "scrollHeight", {
      configurable: true,
      get: () => 300,
    })
    Object.defineProperty(inner, "clientHeight", {
      configurable: true,
      get: () => 300,
    })

    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === outer || el === inner) {
        return { ...style, overflowY: "auto" } as CSSStyleDeclaration
      }
      return style
    })

    expect(findScrollableParent(child)).toBe(outer)

    vi.restoreAllMocks()
  })

  it("finds an ancestor that is actually overflowing even without overflow-y set", () => {
    const parent = document.createElement("div")
    const child = document.createElement("div")
    parent.appendChild(child)

    Object.defineProperty(parent, "scrollHeight", {
      configurable: true,
      get: () => 600,
    })
    Object.defineProperty(parent, "clientHeight", {
      configurable: true,
      get: () => 300,
    })

    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === parent) {
        return { ...style, overflowY: "visible" } as CSSStyleDeclaration
      }
      return style
    })

    expect(findScrollableParent(child)).toBe(parent)

    vi.restoreAllMocks()
  })

  it("does not treat overflow-y:hidden ancestors as scrollable even if content overflows", () => {
    const parent = document.createElement("div")
    const child = document.createElement("div")
    parent.appendChild(child)

    Object.defineProperty(parent, "scrollHeight", {
      configurable: true,
      get: () => 600,
    })
    Object.defineProperty(parent, "clientHeight", {
      configurable: true,
      get: () => 300,
    })

    const original = window.getComputedStyle
    vi.spyOn(window, "getComputedStyle").mockImplementation((el) => {
      const style = original(el)
      if (el === parent) {
        return { ...style, overflowY: "hidden" } as CSSStyleDeclaration
      }
      return style
    })

    expect(findScrollableParent(child)).toBeNull()

    vi.restoreAllMocks()
  })
})
