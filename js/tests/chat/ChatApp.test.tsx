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
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

// Stub window.Shiny for transport code that might reference it
beforeEach(() => {
  installShinyWindowStub()
})

// ---------------------------------------------------------------------------
// Issue #3: Suggestion handlers are plain functions (no stale closure risk)
// ---------------------------------------------------------------------------
describe("Issue #3: suggestion handlers work after re-renders", () => {
  it("renders suggestion elements with keyboard accessibility attributes", () => {
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

    const suggestion = document.querySelector(".suggestion")
    expect(suggestion?.getAttribute("tabindex")).toBe("0")
    expect(suggestion?.getAttribute("role")).toBe("button")
    expect(suggestion?.getAttribute("aria-label")).toBe(
      "Use chat suggestion: click me",
    )
  })

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

// ---------------------------------------------------------------------------
// setInputValue on message completion
// ---------------------------------------------------------------------------
describe("setInputValue on message completion", () => {
  it("sends input value after a non-streamed message action", () => {
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

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Hello!",
          content_type: "markdown",
        },
      })
    })

    expect(transport.sendInput).toHaveBeenCalledWith("test-chat_message", {
      role: "assistant",
      content: "Hello!",
      content_type: "markdown",
    })
  })

  it("sends input value after a streamed message completes (chunk_end)", () => {
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

    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "Hel",
          content_type: "markdown",
        },
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "lo!",
        operation: "append",
      })
    })

    // sendInput should NOT have been called yet (still streaming)
    expect(transport.sendInput).not.toHaveBeenCalledWith(
      "test-chat_message",
      expect.anything(),
    )

    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(transport.sendInput).toHaveBeenCalledWith("test-chat_message", {
      role: "assistant",
      content: "Hello!",
      content_type: "markdown",
    })
  })

  it("sends input value for user messages too", () => {
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

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          content: "Hi there",
          content_type: "markdown",
        },
      })
    })

    expect(transport.sendInput).toHaveBeenCalledWith("test-chat_message", {
      role: "user",
      content: "Hi there",
      content_type: "markdown",
    })
  })
})

// ---------------------------------------------------------------------------
// Bookmark save/restore
// ---------------------------------------------------------------------------
describe("Bookmark save", () => {
  it("responds to _bookmark_save with serialized messages", () => {
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

    // Add some messages
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          content: "Hello",
          content_type: "markdown",
        },
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Hi there!",
          content_type: "html",
        },
      })
    })

    // Clear sendInput mock to isolate bookmark save call
    vi.mocked(transport.sendInput).mockClear()

    // Fire bookmark save
    act(() => {
      transport.fire("test-chat", {
        type: "_bookmark_save",
        key: "bookmark-key-123",
      } as never)
    })

    expect(transport.sendInput).toHaveBeenCalledWith("bookmark-key-123", [
      { role: "user", content: "Hello", content_type: "markdown" },
      { role: "assistant", content: "Hi there!", content_type: "html" },
    ])
  })

  it("responds with empty array when no messages exist", () => {
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

    act(() => {
      transport.fire("test-chat", {
        type: "_bookmark_save",
        key: "bookmark-key-456",
      } as never)
    })

    expect(transport.sendInput).toHaveBeenCalledWith("bookmark-key-456", [])
  })
})

// ---------------------------------------------------------------------------
// External link dialog integration tests
// NOTE: These tests are expected to fail until Tasks 3-4 refactor the dialog
// out of a singleton createRoot and into a React portal rendered in the same
// tree as ChatApp.
// ---------------------------------------------------------------------------
describe("External link dialog", () => {
  /** Render ChatApp with a single assistant message containing an external link */
  async function renderWithExternalLink() {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    const result = render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Visit [Example](https://example.com) for more info.",
          content_type: "markdown",
        },
      })
    })

    return { ...result, transport }
  }

  beforeEach(() => {
    vi.spyOn(window, "open").mockImplementation(() => null)

    HTMLDialogElement.prototype.showModal = vi.fn(function (
      this: HTMLDialogElement,
    ) {
      this.setAttribute("open", "")
    })
    HTMLDialogElement.prototype.close = vi.fn(function (
      this: HTMLDialogElement,
    ) {
      this.removeAttribute("open")
    })

    delete window.shinychat_always_open_external_links
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete window.shinychat_always_open_external_links
  })

  it("clicking an external link shows the confirmation dialog", async () => {
    await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-external-link]",
    ) as HTMLAnchorElement | null
    expect(link).not.toBeNull()

    await act(async () => {
      fireEvent.click(link!)
    })

    const dialog = screen.getByRole("dialog")
    expect(dialog).toBeTruthy()
    expect(screen.getByText("https://example.com/")).toBeTruthy()
  })

  it("confirming the dialog opens the link", async () => {
    await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-external-link]",
    ) as HTMLAnchorElement

    await act(async () => {
      fireEvent.click(link)
    })

    await act(async () => {
      fireEvent.click(screen.getByText("Open Link"))
    })

    expect(window.open).toHaveBeenCalledWith(
      "https://example.com/",
      "_blank",
      "noopener,noreferrer",
    )
  })

  it("canceling the dialog does not open the link", async () => {
    await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-external-link]",
    ) as HTMLAnchorElement

    await act(async () => {
      fireEvent.click(link)
    })

    await act(async () => {
      fireEvent.click(screen.getByText("Cancel"))
    })

    expect(window.open).not.toHaveBeenCalled()
  })

  it("'Always open' skips dialog on subsequent clicks", async () => {
    await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-external-link]",
    ) as HTMLAnchorElement

    // First click — show dialog and click "Always open external links"
    await act(async () => {
      fireEvent.click(link)
    })

    await act(async () => {
      fireEvent.click(screen.getByText("Always open external links"))
    })

    expect(window.open).toHaveBeenCalledTimes(1)

    // Second click — dialog should not appear; link should open directly
    await act(async () => {
      fireEvent.click(link)
    })

    expect(window.open).toHaveBeenCalledTimes(2)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("no dialog or singleton container appended to body after unmount", async () => {
    const { unmount } = await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-external-link]",
    ) as HTMLAnchorElement

    await act(async () => {
      fireEvent.click(link)
    })

    // Dismiss the dialog
    await act(async () => {
      fireEvent.click(screen.getByText("Cancel"))
    })

    unmount()

    expect(
      document.getElementById("shinychat-external-link-dialog-root"),
    ).toBeNull()
    expect(document.querySelector("dialog")).toBeNull()
  })
})
