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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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

    // transport.sendInput should have been called via the container ref.
    // Upload is not enabled here, so the wire shape is a bare string.
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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

// ---------------------------------------------------------------------------
// greeting_dismissed Shiny input
// ---------------------------------------------------------------------------
describe("greeting_dismissed Shiny input", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  function renderWithGreeting(elementId = "test-chat") {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    const result = render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId={elementId}
        inputId={`${elementId}_input`}
        uploadAccept={[]}
        maxUploadSize={30000000}
      />,
    )

    // Send a visible greeting
    act(() => {
      transport.fire(elementId, {
        type: "greeting",
        content: "Hello!",
        content_type: "markdown",
        options: { dismissible: true },
      })
    })

    return { ...result, transport }
  }

  /** Drive the greeting through visible → dismissing → dismissed and return mocked setInputValue. */
  function dismissGreeting(transport: ReturnType<typeof createMockTransport>) {
    const setInputValue = vi.mocked(
      (
        window as unknown as {
          Shiny: { setInputValue: ReturnType<typeof vi.fn> }
        }
      ).Shiny.setInputValue,
    )

    // INPUT_SENT: visible → dismissing
    act(() => {
      transport.fire("test-chat", {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
    })

    // greeting_dismissed reducer action: dismissing → dismissed
    // (This is the action the ChatGreeting animation callback dispatches when
    // the dismiss animation completes. In jsdom there is no animation, so we
    // fire the action directly to reach the "dismissed" state.)
    act(() => {
      transport.fire("test-chat", { type: "greeting_dismissed" })
    })

    return setInputValue
  }

  it("calls setInputValue with {elementId}_greeting_dismissed when greeting transitions to dismissed", () => {
    const { transport } = renderWithGreeting()

    const setInputValue = dismissGreeting(transport)

    const calls = setInputValue.mock.calls
    const dismissedCall = calls.find(
      ([name]: [string]) => name === "test-chat_greeting_dismissed",
    )
    expect(dismissedCall).toBeDefined()
    expect(dismissedCall![0]).toBe("test-chat_greeting_dismissed")
    expect(typeof dismissedCall![1]).toBe("number")
  })

  it("calls setInputValue with null when greeting is cleared after being dismissed", () => {
    const { transport } = renderWithGreeting()

    const setInputValue = dismissGreeting(transport)
    setInputValue.mockClear()

    // Clear the greeting entirely — transitions greetingIsDismissed back to false
    act(() => {
      transport.fire("test-chat", { type: "greeting_clear" })
    })

    const calls = setInputValue.mock.calls
    const nullCall = calls.find(
      ([name, value]: [string, unknown]) =>
        name === "test-chat_greeting_dismissed" && value === null,
    )
    expect(nullCall).toBeDefined()
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
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
