import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

// jsdom's contenteditable div doesn't support fireEvent.change, so the edit
// box's real ProseMirror editor can't be typed into (see the skipped test
// below). Swap in the textarea-based fake for tests that simulate editing.
vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

beforeEach(() => {
  installShinyWindowStub()
})

// The history drawer (rendered once historyEnabled becomes true) checks
// prefers-reduced-motion, which jsdom doesn't implement.
function mockMatchMedia(reducedMotion: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: reducedMotion,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }),
  )
}

describe("ChatApp integration: full message flow", () => {
  it.skip("user message triggers transport.sendInput", async () => {
    // Skipped: TipTap's contenteditable div does not support fireEvent.change
    // (no value setter). Typing into ProseMirror in jsdom requires low-level
    // editor command dispatch rather than DOM event simulation.
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

    await act(async () => {
      fireEvent.change(editorEl, { target: { value: "Hello from user" } })
      fireEvent.keyDown(editorEl, { code: "Enter", key: "Enter" })
    })

    // Upload is not enabled here, so the wire shape is a bare string.
    expect(transport.sendInput).toHaveBeenCalledWith(
      "test-input",
      "Hello from user",
    )
  })

  it("streaming chunks render assistant message", async () => {
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

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "Hello world",
        operation: "append",
      })
    })

    await act(async () => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(screen.getByText("Hello world")).toBeTruthy()
  })

  it("streaming dot appears during streaming and disappears after chunk_end", async () => {
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

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "Streaming...",
        operation: "append",
      })
    })

    expect(document.querySelector(".markdown-stream-dot")).not.toBeNull()

    await act(async () => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(document.querySelector(".markdown-stream-dot")).toBeNull()
  })

  it("keeps web activity expanded when a streaming message settles", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[]}
        maxUploadSize={null}
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                '<shiny-web-search query="R 4.5.0 release date"></shiny-web-search>',
              content_type: "markdown",
            },
          ],
        },
      })
    })

    const header = screen.getByRole("button", { name: "Searched the web" })
    fireEvent.click(header)
    expect(header).toHaveAttribute("aria-expanded", "true")

    await act(async () => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(
      screen.getByRole("button", { name: "Searched the web" }),
    ).toHaveAttribute("aria-expanded", "true")
  })

  it("renders a non-streaming assistant reply", async () => {
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

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Complete reply", content_type: "markdown" }],
        },
      })
    })

    expect(screen.getByText("Complete reply")).toBeTruthy()
  })

  it("scroll-to-bottom button is hidden when at bottom (default state)", async () => {
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

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Reply", content_type: "markdown" }],
        },
      })
    })

    // When at bottom (default), the scroll-to-bottom button should not appear
    expect(document.querySelector(".shiny-chat-scroll-to-bottom")).toBeNull()
  })
})

describe("ChatApp integration: editable messages gated by history state", () => {
  function renderChatApp(transport: ReturnType<typeof createMockTransport>) {
    return render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={["image/png"]}
        maxUploadSize={30000000}
        placeholder="Type..."
      />,
    )
  }

  it("does not render the edit button on a user message when history was never enabled", async () => {
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hello", content_type: "markdown" }],
        },
      })
    })

    // No history_update action has been fired, so the server never
    // registered a `_message_edit` listener. The control must not render --
    // otherwise clicking it silently does nothing (no new response, no
    // visible feedback).
    expect(screen.queryByRole("button", { name: /edit message/i })).toBeNull()
  })

  it("renders the edit button and forwards edits via transport.sendMessageEdit once history is enabled", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const { container } = renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hello", content_type: "markdown" }],
        },
      })
    })

    fireEvent.click(screen.getByRole("button", { name: /edit message/i }))
    const textarea = container.querySelector(
      ".shiny-chat-edit-box textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: "edited hello" } })
    fireEvent.click(
      container.querySelector(".shiny-chat-btn-send") as HTMLElement,
    )

    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      "test-chat",
      0,
      "edited hello",
      [],
    )
  })

  it("routes drawer actions through the history store and disables them while streaming", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    fireEvent.click(
      screen.getByRole("button", { name: /conversation history/i }),
    )
    fireEvent.click(screen.getByRole("button", { name: /new conversation/i }))
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("test-chat")

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })

    fireEvent.click(
      screen.getByRole("button", { name: /conversation history/i }),
    )
    expect(
      screen.getByRole("button", { name: /new conversation/i }),
    ).toHaveProperty("disabled", true)
  })

  it("forwards sibling navigation via transport.sendMessageNavigate once history is enabled", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hello", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_siblings",
        data: { 0: { index: 0, total: 2 } },
      })
    })

    fireEvent.click(screen.getByRole("button", { name: /next version/i }))

    expect(transport.sendMessageNavigate).toHaveBeenCalledWith(
      "test-chat",
      0,
      "next",
    )
  })

  it("disables sibling navigation until the server acknowledges it", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "hello", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_siblings",
        data: { 0: { index: 0, total: 2 } },
      })
    })

    const previous = screen.getByRole("button", {
      name: /previous version/i,
    })
    const next = screen.getByRole("button", { name: /next version/i })
    expect(previous).toHaveProperty("disabled", true)
    expect(next).toHaveProperty("disabled", false)

    fireEvent.click(next)

    expect(previous).toHaveProperty("disabled", true)
    expect(next).toHaveProperty("disabled", true)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(next).toHaveProperty("disabled", false)
  })
})
