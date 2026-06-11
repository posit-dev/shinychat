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
          segments: [
            {
              content:
                "Hello! <span class='suggestion' data-suggestion='click me'>click me</span>",
              content_type: "html",
            },
          ],
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

  it.skip("suggestion click works after state changes trigger re-renders", async () => {
    // Skipped: TipTap's prosemirror-view calls getClientRects() on focus after
    // a suggestion click, which is not implemented in jsdom and throws an
    // uncaught exception.
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

    const editorEl = screen.getByRole("textbox", { name: "Chat message" })

    // Trigger multiple re-renders via state changes
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "Hello! <span class='suggestion' data-suggestion='click me'>click me</span>",
              content_type: "html",
            },
          ],
        },
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        placeholder: "New placeholder",
      })
    })

    // If a suggestion element was rendered, clicking it should set the editor value.
    // (The handlers are now plain functions, so no stale closure concern.)
    const suggestion = document.querySelector(".suggestion")
    if (suggestion) {
      fireEvent.click(suggestion)
      expect(editorEl.textContent).toBe("click me")
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

    const editorEl = screen.getByRole("textbox", { name: "Chat message" })

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "hello world",
      })
    })

    expect(editorEl.textContent).toBe("hello world")
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

    const editor = screen.getByRole("textbox", {
      name: "Chat message",
    }) as HTMLDivElement

    // Set some text in the editor first via update_input (no submit)
    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "existing text",
      })
    })

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
    expect(editor.textContent).toBe("existing text")
  })

  it.skip("update_input with focus=true forwards to container handle", () => {
    // Skipped: TipTap's editor.commands.focus() calls getClientRects() via
    // prosemirror-view's scrollToSelection, which is not implemented in jsdom.
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

    const editorEl = screen.getByRole("textbox", { name: "Chat message" })

    // Focus should be forwarded via the container ref
    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        focus: true,
      })
    })

    expect(document.activeElement).toBe(editorEl)
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
          segments: [
            {
              content: "Visit [Example](https://example.com) for more info.",
              content_type: "markdown",
            },
          ],
        },
      })
    })

    return { ...result, transport }
  }

  beforeEach(() => {
    vi.spyOn(window, "open").mockImplementation(() => ({}) as Window)

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
      "a[data-shinychat-link]",
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
      "a[data-shinychat-link]",
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
      "a[data-shinychat-link]",
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
      "a[data-shinychat-link]",
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

  it("same-origin link opens directly without dialog", async () => {
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

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content: "Visit [this page](/some-path) for more info.",
              content_type: "markdown",
            },
          ],
        },
      })
    })

    const link = document.querySelector(
      "a[data-shinychat-link]",
    ) as HTMLAnchorElement
    expect(link).not.toBeNull()

    await act(async () => {
      fireEvent.click(link!)
    })

    expect(window.open).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("no dialog or singleton container appended to body after unmount", async () => {
    const { unmount } = await renderWithExternalLink()

    const link = document.querySelector(
      "a[data-shinychat-link]",
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

describe("server-controlled cancel", () => {
  function startStreaming(transport: ReturnType<typeof createMockTransport>) {
    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })
  }

  it("does not show the stop button while streaming when enableCancel is unset", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        cancelId="test-chat_cancel"
      />,
    )

    startStreaming(transport)

    expect(screen.queryByRole("button", { name: "Stop generating" })).toBeNull()
  })

  it("shows the stop button after an update_cancel message enables it", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        cancelId="test-chat_cancel"
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "update_cancel",
        enable_cancel: true,
      })
    })

    startStreaming(transport)

    expect(screen.getByRole("button", { name: "Stop generating" })).toBeTruthy()
  })
})
