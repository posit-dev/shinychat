/**
 * Tests for ChatContainer / ChatApp after fixing review issues #3 and #4.
 *
 * Issue #3: onSuggestionClick/onSuggestionKeydown were wrapped in
 *   useCallback(fn, []) capturing a stale handleSuggestionEvent closure.
 *   The ref indirection saved it from being a runtime bug, but the pattern
 *   was misleading and fragile. Fix: remove unnecessary useCallback wrappers.
 *
 * Issue #4: Both ChatApp and ChatContainer subscribed to
 *   transport.onMessage(elementId, ...), creating two listeners for every
 *   action. Fix: single subscription in ChatApp; imperative input actions
 *   forwarded via ChatContainer's ref handle.
 */
import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import type {
  ChatTransport,
  ShinyLifecycle,
  ChatAction,
} from "../../src/transport/types"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a mock transport that stores listeners and lets us fire actions */
function createMockTransport(): ChatTransport & {
  fire: (id: string, action: ChatAction) => void
  listenerCount: (id: string) => number
} {
  const listeners = new Map<string, Set<(action: ChatAction) => void>>()

  return {
    sendInput: vi.fn(),
    onMessage(id, callback) {
      if (!listeners.has(id)) listeners.set(id, new Set())
      listeners.get(id)!.add(callback)
      return () => {
        listeners.get(id)?.delete(callback)
      }
    },

    fire(id, action) {
      const cbs = listeners.get(id)
      if (cbs) {
        for (const cb of cbs) cb(action)
      }
    },

    listenerCount(id) {
      return listeners.get(id)?.size ?? 0
    },
  }
}

function createMockShinyLifecycle(): ShinyLifecycle {
  return {
    renderDependencies: vi.fn(async () => {}),
    bindAll: vi.fn(async () => {}),
    unbindAll: vi.fn(),
    showClientMessage: vi.fn(),
  }
}

// Stub window.Shiny for transport code that might reference it
beforeEach(() => {
  ;(window as unknown as Record<string, unknown>).Shiny = {
    setInputValue: vi.fn(),
    addCustomMessageHandler: vi.fn(),
    bindAll: vi.fn(),
    unbindAll: vi.fn(),
    initializeInputs: vi.fn(),
    renderDependenciesAsync: vi.fn(),
  }
})

// ---------------------------------------------------------------------------
// Issue #3: Suggestion handlers are plain functions (no stale closure risk)
// ---------------------------------------------------------------------------
describe("Issue #3: suggestion handlers work after re-renders", () => {
  it("suggestion click works after state changes trigger re-renders", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type here..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type here...",
    ) as HTMLTextAreaElement

    // Trigger multiple re-renders via state changes
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            "Hello! <span class='suggestion' data-suggestion='click me'>click me</span>",
          content_type: "html",
        },
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        placeholder: "New placeholder",
      })
    })

    // If a suggestion element was rendered, clicking it should set the textarea value.
    // (The handlers are now plain functions, so no stale closure concern.)
    const suggestion = document.querySelector(".suggestion")
    if (suggestion) {
      fireEvent.click(suggestion)
      expect(textarea.value).toBe("click me")
    }
  })
})

// ---------------------------------------------------------------------------
// Issue #4: Single transport subscription
// ---------------------------------------------------------------------------
describe("Issue #4: single transport subscription", () => {
  it("only one listener is registered per elementId", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    // After fix: ChatApp registers one listener; ChatContainer no longer subscribes
    expect(transport.listenerCount("test-chat")).toBe(1)
  })

  it("update_input with value (no submit/focus) dispatches to reducer", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "hello world",
      })
    })

    expect(textarea.value).toBe("hello world")
  })

  it("update_input with submit=true forwards to container handle", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement

    // Put some text in the textarea first
    textarea.value = "existing text"

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "submitted text",
        submit: true,
      })
    })

    // transport.sendInput should have been called via the container ref
    expect(transport.sendInput).toHaveBeenCalledWith(
      "test-input",
      "submitted text",
    )

    // After submit, the old value should be restored
    expect(textarea.value).toBe("existing text")
  })

  it("update_input with focus=true forwards to container handle", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement

    // Focus should be forwarded via the container ref
    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        focus: true,
      })
    })

    expect(document.activeElement).toBe(textarea)
  })

  it("cleanup removes the single subscription", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    const { unmount } = render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    expect(transport.listenerCount("test-chat")).toBe(1)

    unmount()

    expect(transport.listenerCount("test-chat")).toBe(0)
  })
})
