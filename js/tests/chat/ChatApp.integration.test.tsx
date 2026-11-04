import { describe, it, expect, beforeEach, afterEach, vi } from "vitest"
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react"
import { StrictMode } from "react"
import { ChatApp } from "../../src/chat/ChatApp"
import { getHistoryStore } from "../../src/chat/historyStore"
import type { ChatMessageData } from "../../src/chat/state"
import type { ChatAction } from "../../src/transport/types"
import { STREAM_IDLE_MS } from "../../src/markdown/useStreamIdle"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

// jsdom's contenteditable div doesn't support fireEvent.change, so use the
// textarea-based fake for tests that simulate composer and edit input.
vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

vi.mock("../../src/chat/attachments", async (orig) => {
  const actual = await orig<typeof import("../../src/chat/attachments")>()
  return {
    ...actual,
    processFile: vi.fn(async (file: File) => ({
      file: {
        id: `att-${file.name}`,
        type: file.type,
        family: actual.attachmentFamily(file.type) ?? "document",
        dataUrl: `data:${file.type};base64,FAKE`,
        name: file.name,
        size: file.size,
      },
      wasDownscaled: false,
      wasConverted: false,
    })),
  }
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
  it("ordinary user message triggers transport.sendInput", async () => {
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

    // Correlation is sent even without the upload affordance.
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
      text: "Hello from user",
      attachments: [],
      client_message_id: expect.any(String),
    })
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

    // The buffered tail drains quickly after chunk_end rather than at once.
    expect(await screen.findByText("Hello world")).toBeTruthy()
  })

  it("streaming dot appears only when a stream stalls and disappears after chunk_end", async () => {
    vi.useFakeTimers()
    try {
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

      const dot = () => document.querySelector(".markdown-stream-dot")

      // Text is arriving: no dot.
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(dot()).toBeNull()

      // The stream stalls (buffer drained, no new chunks): the dot appears.
      // Separate acts so React commits the drained text (starting the idle
      // clock) before time advances past the threshold.
      act(() => {
        vi.advanceTimersByTime(1000)
      })
      expect(dot()).toBeNull()
      act(() => {
        vi.advanceTimersByTime(STREAM_IDLE_MS + 100)
      })
      expect(dot()).not.toBeNull()

      // Content resumes: the dot goes away as soon as new text is revealed.
      await act(async () => {
        transport.fire("test-chat", {
          type: "chunk",
          content: " more",
          operation: "append",
        })
      })
      act(() => {
        vi.advanceTimersByTime(100)
      })
      expect(dot()).toBeNull()

      await act(async () => {
        transport.fire("test-chat", { type: "chunk_end" })
      })
      act(() => {
        vi.advanceTimersByTime(1000)
      })

      expect(dot()).toBeNull()
    } finally {
      vi.useRealTimers()
    }
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
          segments: [],
        },
      })
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "block_insert",
        block: {
          type: "web_search",
          version: 1,
          query: "R 4.5.0 release date",
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
  function renderChatApp(
    transport: ReturnType<typeof createMockTransport>,
    enableUpload?: boolean,
    initialMessages?: ChatMessageData[],
  ) {
    return render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={["image/png"]}
        maxUploadSize={30000000}
        placeholder="Type..."
        enableUpload={enableUpload}
        initialMessages={initialMessages}
      />,
    )
  }

  it("rechecks history admission before an imperative input dispatches", async () => {
    const transport = createMockTransport()
    const { container } = render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="direct-submit-recheck"
        inputId="direct-submit-input"
        uploadAccept={["image/png"]}
        maxUploadSize={30000000}
        placeholder="Type..."
        enableUpload
      />,
    )

    const draft = container.querySelector(
      ".shiny-chat-composer textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(draft, { target: { value: "preserved draft" } })
    const fileInput = container.querySelector(
      ".shiny-chat-composer input[type=file]",
    ) as HTMLInputElement
    await act(async () => {
      fireEvent.change(fileInput, {
        target: {
          files: [new File(["draft"], "draft.png", { type: "image/png" })],
        },
      })
    })
    await waitFor(() => {
      expect(
        container.querySelectorAll(
          ".shiny-chat-composer .shiny-chat-input-thumbnail",
        ),
      ).toHaveLength(1)
    })
    expect(
      screen.getByRole("button", { name: "Send message" }),
    ).not.toBeDisabled()

    const historyStore = getHistoryStore("direct-submit-recheck")
    await act(async () => {
      historyStore.seedCompletionV2TransitionProtocol()
      transport.fire("direct-submit-recheck", {
        type: "update_input",
        value: "blocked server submission",
        submit: true,
      })
    })

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.queryByText("blocked server submission")).toBeNull()
    expect(draft).toHaveValue("preserved draft")
    expect(
      container.querySelectorAll(
        ".shiny-chat-composer .shiny-chat-input-thumbnail",
      ),
    ).toHaveLength(1)
    expect(container.querySelectorAll(".shiny-chat-user-message")).toHaveLength(
      0,
    )
  })

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

  it("renders a server-staged retry without sending its input again", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "retry me", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_exchange_metadata",
        data: { 0: { status: "error", retryable: true } },
      })
    })

    fireEvent.click(screen.getByRole("button", { name: "Retry message" }))
    const requestId = vi.mocked(transport.sendMessageResubmit).mock
      .calls[0]?.[3]
    expect(requestId).toEqual(expect.any(String))

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 0,
        content: "retry me",
        attachments: [],
        exchange_id: "staged-retry",
      })
    })

    expect(screen.getByText("retry me")).toBeTruthy()
    expect(transport.sendInput).not.toHaveBeenCalled()
  })

  it.each([
    ["missing exchange ID", { exchange_id: undefined }],
    ["empty exchange ID", { exchange_id: "" }],
    ["non-string exchange ID", { exchange_id: 42 }],
    ["missing request ID", { requestId: null }],
    ["negative index", { index: -1 }],
    ["out-of-bounds index", { index: 5 }],
    ["invalid content", { content: null }],
    ["invalid attachments", { attachments: null }],
  ])(
    "ignores a malformed projection with %s",
    async (_description, invalidFields) => {
      mockMatchMedia(false)
      const transport = createMockTransport()
      const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
      renderChatApp(transport)

      await act(async () => {
        transport.fire("test-chat", {
          type: "history_update",
          enabled: true,
          conversations: [],
          active_id: null,
          transition_protocol: "completion-v2",
        })
        transport.fire("test-chat", {
          type: "message",
          message: {
            role: "user",
            segments: [{ content: "original", content_type: "markdown" }],
          },
        })
      })
      fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
      fireEvent.change(screen.getByPlaceholderText("Edit message"), {
        target: { value: "replacement" },
      })
      fireEvent.click(screen.getByRole("button", { name: "Save and resend" }))
      const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]?.[4]
      expect(requestId).toEqual(expect.any(String))

      await act(async () => {
        transport.fire("test-chat", {
          type: "history_edit_projection",
          requestId: requestId as string,
          index: 0,
          content: "replacement",
          attachments: [],
          exchange_id: "staged-node",
          ...invalidFields,
        } as unknown as ChatAction)
      })
      expect(warn).toHaveBeenCalledWith(
        "[shinychat] Malformed history edit projection; dropping.",
      )
      warn.mockRestore()
      expect(transport.sendInput).not.toHaveBeenCalled()
      expect(screen.getByText("original")).toBeTruthy()
      expect(screen.queryByText("replacement")).toBeNull()
      expect(
        screen.getByRole("button", { name: "Send message" }),
      ).toBeDisabled()
      expect(getHistoryStore("test-chat").getSnapshot().busy).toBe(false)

      // Rejection does not consume the correlated transition.
      await act(async () => {
        transport.fire("test-chat", {
          type: "history_edit_projection",
          requestId: requestId as string,
          index: 0,
          content: "replacement",
          attachments: [],
          exchange_id: "staged-node",
        })
      })
      expect(screen.queryByText("original")).toBeNull()
      expect(screen.getByText("replacement")).toBeTruthy()
      expect(transport.sendInput).not.toHaveBeenCalled()
    },
  )

  it("leaves the selected branch and busy state unchanged when an invalid projection is dropped", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    renderChatApp(transport)
    const store = getHistoryStore("test-chat")
    fireEvent.change(screen.getByRole("textbox", { name: "Chat message" }), {
      target: { value: "draft" },
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "selected branch", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "selected reply", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: null,
        index: 0,
        content: "uncorrelated replacement",
        attachments: [],
        exchange_id: "uncorrelated-node",
      } as unknown as ChatAction)
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: "stale-request",
        index: 0,
        content: "stale replacement",
        attachments: [],
      } as unknown as ChatAction)
    })
    expect(store.getSnapshot().historyTransitionPending).toBeNull()
    expect(store.getSnapshot().busy).toBe(false)
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()
    expect(screen.getByText("selected branch")).toBeTruthy()
    expect(screen.getByText("selected reply")).toBeTruthy()
    expect(screen.queryByText("stale replacement")).toBeNull()
    expect(screen.queryByText("uncorrelated replacement")).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
    fireEvent.change(screen.getByPlaceholderText("Edit message"), {
      target: { value: "replacement" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save and resend" }))
    const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]?.[4]
    expect(requestId).toEqual(expect.any(String))
    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 0,
        content: "replacement",
        attachments: [],
      } as unknown as ChatAction)
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 1,
        content: "replacement for assistant",
        attachments: [],
        exchange_id: "staged-node",
      })
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: "stale-request",
      })
    })
    expect(store.getSnapshot().historyTransitionPending).toBe(requestId)
    expect(store.getSnapshot().busy).toBe(false)
    expect(screen.getByText("selected branch")).toBeTruthy()
    expect(screen.getByText("selected reply")).toBeTruthy()
    await act(async () => {
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: requestId as string,
      })
    })
    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 0,
        content: "late replacement",
        attachments: [],
        exchange_id: "late-node",
      })
    })
    expect(store.getSnapshot().historyTransitionPending).toBeNull()
    expect(store.getSnapshot().busy).toBe(false)
    expect(screen.getByRole("button", { name: "Send message" })).toBeEnabled()
    expect(screen.getByText("selected branch")).toBeTruthy()
    expect(screen.getByText("selected reply")).toBeTruthy()
    expect(screen.queryByText("late replacement")).toBeNull()
    expect(transport.sendInput).not.toHaveBeenCalled()
    warn.mockRestore()
  })

  it("projects a matching edit without consuming the composer draft", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const { container } = renderChatApp(transport)
    const draftFile = new File(["draft"], "draft.png", { type: "image/png" })
    const replacementAttachments = [
      {
        mime: "image/png" as const,
        data_url: "data:image/png;base64,REPLACEMENT",
        name: "replacement.png",
        size: 3,
      },
    ]

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "update_upload",
        enable_upload: true,
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "prefix", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "custom prefix", content_type: "html" }],
        },
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "replace me", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "abandoned reply", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_siblings",
        data: { 2: { index: 0, total: 2 } },
      })
    })

    const composer = container.querySelector(
      ".shiny-chat-composer textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(composer, { target: { value: "preserved draft" } })
    const composerFileInput = container.querySelector(
      ".shiny-chat-composer input[type=file]",
    ) as HTMLInputElement
    await act(async () => {
      fireEvent.change(composerFileInput, { target: { files: [draftFile] } })
    })
    await waitFor(() => {
      expect(
        container.querySelectorAll(
          ".shiny-chat-composer .shiny-chat-input-thumbnail",
        ),
      ).toHaveLength(1)
    })

    const targetUser = screen
      .getByText("replace me")
      .closest(".shiny-chat-user-message") as HTMLElement
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-edit-btn") as HTMLElement,
    )
    const editInput = targetUser.querySelector(
      ".shiny-chat-edit-box textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(editInput, { target: { value: "replacement" } })
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-btn-send") as HTMLElement,
    )

    const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]?.[4]
    expect(requestId).toEqual(expect.any(String))
    expect(
      screen.getByRole("button", { name: /send message/i }),
    ).toHaveProperty("disabled", true)
    expect(
      screen.getByRole("button", { name: /next version/i }),
    ).toHaveProperty("disabled", true)
    fireEvent.click(
      screen.getByRole("button", { name: /conversation history/i }),
    )
    expect(
      screen.getByRole("button", { name: /new conversation/i }),
    ).toHaveProperty("disabled", true)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: "stale",
        index: 2,
        content: "stale replacement",
        attachments: [],
        exchange_id: "stale-node",
      })
    })
    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.getByText("replace me")).toBeTruthy()

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 2,
        content: "replacement",
        attachments: replacementAttachments,
        exchange_id: "staged-node",
      })
      // A duplicate delivery cannot replace the already projected row.
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 2,
        content: "duplicate replacement",
        attachments: replacementAttachments,
        exchange_id: "staged-node",
      })
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: requestId as string,
      })
    })

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.getByRole("button", { name: "Loading" })).toHaveAttribute(
      "aria-disabled",
      "true",
    )
    expect(screen.getByText("custom prefix")).toBeTruthy()
    expect(screen.queryByText("replace me")).toBeNull()
    expect(screen.queryByText("abandoned reply")).toBeNull()
    expect(screen.queryByText("duplicate replacement")).toBeNull()
    const projectedUserMessages = container.querySelectorAll(
      ".shiny-chat-user-message",
    )
    expect(
      projectedUserMessages[projectedUserMessages.length - 1],
    ).toHaveTextContent("replacement")
    expect(
      container.querySelector(".shiny-chat-composer textarea"),
    ).toHaveValue("preserved draft")
    expect(
      container.querySelectorAll(
        ".shiny-chat-composer .shiny-chat-input-thumbnail",
      ),
    ).toHaveLength(1)

    const projectedRow = screen
      .getByText("replacement")
      .closest(".shiny-chat-user-message")
    await act(async () => {
      transport.fire("test-chat", {
        type: "update_exchange_metadata",
        data: {
          2: {
            status: "error",
            retryable: true,
            preparation_failed: true,
            error_message: "Message not sent.",
          },
        },
      })
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: "conversation",
        active_read_only: true,
        active_can_resubmit: true,
        transition_protocol: "completion-v2",
      })
    })
    expect(screen.queryByRole("button", { name: "Loading" })).toBeNull()
    expect(
      screen.getByText("replacement").closest(".shiny-chat-user-message"),
    ).toBe(projectedRow)
    const failureNotice = screen.getByText("This message was not sent.")
    expect(projectedRow).not.toContainElement(failureNotice)
    expect(projectedRow?.nextElementSibling).toBe(failureNotice)
    expect(screen.getByRole("button", { name: "Retry message" })).toBeEnabled()
    expect(container.querySelector(".shiny-chat-composer textarea")).toBe(
      composer,
    )
    expect(composer).toHaveValue("preserved draft")
    expect(composer).not.toBeVisible()
    expect(
      container.querySelectorAll(
        ".shiny-chat-composer .shiny-chat-input-thumbnail",
      ),
    ).toHaveLength(1)
    expect(
      screen.getAllByRole("button", { name: /edit message/i }),
    ).toHaveLength(1)
    fireEvent.click(screen.getByRole("button", { name: "Retry message" }))
    expect(transport.sendMessageResubmit).toHaveBeenCalledTimes(1)
    expect(transport.sendInput).not.toHaveBeenCalled()
  })

  it("clears a downgraded v2 edit transition and ignores its stale projection", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const { container } = renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "replace me", content_type: "markdown" }],
        },
      })
    })

    const targetUser = screen
      .getByText("replace me")
      .closest(".shiny-chat-user-message") as HTMLElement
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-edit-btn") as HTMLElement,
    )
    const editInput = targetUser.querySelector(
      ".shiny-chat-edit-box textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(editInput, { target: { value: "v2 replacement" } })
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-btn-send") as HTMLElement,
    )

    const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]?.[4]
    expect(requestId).toEqual(expect.any(String))

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v1",
      })
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 0,
        content: "stale replacement",
        attachments: [],
        exchange_id: "stale-node",
      })
    })

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.getByText("replace me")).toBeTruthy()

    // The marker was cleared with the capability change, so the v1 edit path
    // is immediately usable and must not carry the obsolete request ID.
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-edit-btn") as HTMLElement,
    )
    const legacyEditInput = targetUser.querySelector(
      ".shiny-chat-edit-box textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(legacyEditInput, {
      target: { value: "v1 replacement" },
    })
    fireEvent.click(
      targetUser.querySelector(".shiny-chat-btn-send") as HTMLElement,
    )
    expect(transport.sendMessageEdit).toHaveBeenLastCalledWith(
      "test-chat",
      0,
      "v1 replacement",
      [],
    )
  })

  it("renders projected attachments when composer uploads are disabled", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const { container } = renderChatApp(transport, false)
    const replacementAttachments = [
      {
        mime: "image/png" as const,
        data_url: "data:image/png;base64,REPLACEMENT",
        name: "replacement.png",
        size: 3,
      },
    ]

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "replace me", content_type: "markdown" }],
        },
      })
    })

    fireEvent.click(screen.getByRole("button", { name: /edit message/i }))
    const editInput = container.querySelector(
      ".shiny-chat-edit-box textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(editInput, { target: { value: "replacement" } })
    fireEvent.click(
      container.querySelector(".shiny-chat-btn-send") as HTMLElement,
    )

    const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]?.[4]
    expect(requestId).toEqual(expect.any(String))

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: "stale",
        index: 0,
        content: "stale replacement",
        attachments: replacementAttachments,
        exchange_id: "stale-node",
      })
    })
    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.getByText("replace me")).toBeTruthy()

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_edit_projection",
        requestId: requestId as string,
        index: 0,
        content: "replacement",
        attachments: replacementAttachments,
        exchange_id: "staged-node",
      })
    })

    expect(transport.sendInput).not.toHaveBeenCalled()
    expect(screen.getByText("replacement")).toBeTruthy()
    expect(
      container.querySelector(".shiny-chat-user-message img"),
    ).toHaveAttribute("src", "data:image/png;base64,REPLACEMENT")
  })

  it("sends an eligible restored retry through the v2 transition transport", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    renderChatApp(transport)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "retry me", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_exchange_metadata",
        data: {
          0: {
            status: "error",
            retryable: true,
            error_message: "The response stream could not be started.",
          },
        },
      })
    })

    expect(
      screen.getByText("The response stream could not be started."),
    ).toBeTruthy()
    fireEvent.click(screen.getByRole("button", { name: "Retry message" }))
    expect(transport.sendMessageResubmit).toHaveBeenCalledWith(
      "test-chat",
      0,
      "retry",
      expect.any(String),
    )
    expect(
      screen.getByRole("button", { name: /send message/i }),
    ).toHaveProperty("disabled", true)
  })

  it("blocks restored retry, edit, and sibling navigation until completion-v2 initializes", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const historyStore = getHistoryStore("test-chat")
    historyStore.seedCompletionV2TransitionProtocol()
    renderChatApp(transport, false, [
      {
        id: "restored-user",
        role: "user",
        content: "restored message",
        streaming: false,
        blocks: [
          {
            type: "content",
            content: "restored message",
            contentType: "markdown",
          },
        ],
        siblings: { index: 0, total: 2 },
        exchange: {
          status: "error",
          retryable: true,
          error_message: "Restored error",
        },
      },
    ])

    await waitFor(() => {
      expect(screen.getByText("restored message")).toBeTruthy()
      expect(screen.getByText("Restored error")).toBeTruthy()
    })
    expect(screen.getByRole("button", { name: "Next version" })).toHaveProperty(
      "disabled",
      true,
    )
    expect(screen.queryByRole("button", { name: "Retry message" })).toBeNull()
    expect(screen.queryByRole("button", { name: "Edit message" })).toBeNull()
    expect(transport.sendMessageNavigate).not.toHaveBeenCalled()
    expect(transport.sendMessageResubmit).not.toHaveBeenCalled()
    expect(transport.sendMessageEdit).not.toHaveBeenCalled()

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
    })

    expect(screen.getByRole("button", { name: "Next version" })).toBeEnabled()
    expect(screen.getByRole("button", { name: "Retry message" })).toBeEnabled()
    fireEvent.click(screen.getByRole("button", { name: "Retry message" }))
    const resubmitRequestId = vi.mocked(transport.sendMessageResubmit).mock
      .calls[0]?.[3]
    expect(resubmitRequestId).toEqual(expect.any(String))
    await act(async () => {
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: resubmitRequestId as string,
      })
    })

    fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
    const editInput = screen.getByPlaceholderText("Edit message")
    expect(editInput).toHaveAccessibleName("Chat message")
    fireEvent.change(editInput, {
      target: { value: "edited restored message" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Save and resend" }))
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      "test-chat",
      0,
      "edited restored message",
      [],
      expect.any(String),
    )
    const editRequestId = vi.mocked(transport.sendMessageEdit).mock
      .calls[0]?.[4]
    expect(editRequestId).toEqual(expect.any(String))
    await act(async () => {
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: editRequestId as string,
      })
    })

    fireEvent.click(screen.getByRole("button", { name: "Next version" }))
    expect(transport.sendMessageNavigate).toHaveBeenCalledWith(
      "test-chat",
      0,
      "next",
      expect.any(String),
    )
  })

  it.each([
    ["Python v1", "completion-v1"],
    ["R", undefined],
  ])(
    "keeps %s history mutations available while ordinary input is pending",
    async (_runtime, transitionProtocol) => {
      mockMatchMedia(false)
      const transport = createMockTransport()
      const { container } = renderChatApp(transport)
      const conversations = [
        {
          id: "legacy",
          title: "Legacy conversation",
          created_at: "2026-09-01T00:00:00.000Z",
          updated_at: "2026-09-01T00:00:00.000Z",
        },
      ]

      await act(async () => {
        transport.fire("test-chat", {
          type: "history_update",
          enabled: true,
          conversations,
          active_id: null,
          ...(transitionProtocol === undefined
            ? {}
            : { transition_protocol: transitionProtocol }),
        })
        transport.fire("test-chat", {
          type: "message",
          message: {
            role: "user",
            segments: [{ content: "legacy target", content_type: "markdown" }],
          },
        })
        transport.fire("test-chat", {
          type: "update_siblings",
          data: { 0: { index: 0, total: 2 } },
        })
      })

      const composer = container.querySelector(
        ".shiny-chat-composer textarea",
      ) as HTMLTextAreaElement
      fireEvent.change(composer, { target: { value: "ordinary input" } })
      fireEvent.click(
        container.querySelector(
          ".shiny-chat-composer .shiny-chat-btn-send",
        ) as HTMLElement,
      )
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
        text: "ordinary input",
        attachments: [],
        client_message_id: expect.any(String),
      })

      const targetUser = screen
        .getByText("legacy target")
        .closest(".shiny-chat-user-message") as HTMLElement
      fireEvent.click(
        targetUser.querySelector(".shiny-chat-edit-btn") as HTMLElement,
      )
      const editInput = targetUser.querySelector(
        ".shiny-chat-edit-box textarea",
      ) as HTMLTextAreaElement
      fireEvent.change(editInput, { target: { value: "legacy edit" } })
      fireEvent.click(
        targetUser.querySelector(".shiny-chat-btn-send") as HTMLElement,
      )
      expect(transport.sendMessageEdit).toHaveBeenCalledWith(
        "test-chat",
        0,
        "legacy edit",
        [],
      )

      const nextVersion = screen.getByRole("button", {
        name: "Next version",
      })
      expect(nextVersion).toBeEnabled()
      fireEvent.click(nextVersion)
      expect(transport.sendMessageNavigate).toHaveBeenCalledWith(
        "test-chat",
        0,
        "next",
      )

      fireEvent.click(
        screen.getByRole("button", { name: /conversation history/i }),
      )
      const newConversation = screen.getByRole("button", {
        name: /new conversation/i,
      })
      expect(newConversation).toBeEnabled()
      fireEvent.click(newConversation)
      expect(transport.sendHistoryNew).toHaveBeenCalledWith("test-chat")

      fireEvent.click(
        screen.getByRole("button", { name: /conversation history/i }),
      )
      fireEvent.click(
        container.querySelector(
          ".shiny-chat-history-itemmenu button",
        ) as HTMLElement,
      )
      fireEvent.click(screen.getByText("Rename"))
      const rename = screen.getByDisplayValue(
        "Legacy conversation",
      ) as HTMLInputElement
      fireEvent.change(rename, { target: { value: "Renamed legacy" } })
      fireEvent.keyDown(rename, { key: "Enter" })
      expect(transport.sendHistoryRename).toHaveBeenCalledWith(
        "test-chat",
        "legacy",
        "Renamed legacy",
      )
    },
  )

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

  it("keeps drawer actions attached through StrictMode effect replay", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()

    render(
      <StrictMode>
        <ChatApp
          transport={transport}
          shinyLifecycle={createMockShinyLifecycle()}
          elementId="test-chat"
          inputId="test-input"
          uploadAccept={["image/png"]}
          maxUploadSize={30000000}
          placeholder="Type..."
        />
      </StrictMode>,
    )

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
    expect(() =>
      fireEvent.click(
        screen.getByRole("button", { name: /new conversation/i }),
      ),
    ).not.toThrow()
    expect(transport.sendHistoryNew).toHaveBeenCalledWith("test-chat")
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

  it("uses the v2 transition marker for sibling navigation without consuming the composer", async () => {
    mockMatchMedia(false)
    const transport = createMockTransport()
    const { container } = renderChatApp(transport, true)
    const draftFile = new File(["draft"], "draft.png", { type: "image/png" })

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "replace me", content_type: "markdown" }],
        },
      })
      transport.fire("test-chat", {
        type: "update_siblings",
        data: { 0: { index: 0, total: 2 } },
      })
    })

    const composer = container.querySelector(
      ".shiny-chat-composer textarea",
    ) as HTMLTextAreaElement
    fireEvent.change(composer, { target: { value: "preserved draft" } })
    const composerFileInput = container.querySelector(
      ".shiny-chat-composer input[type=file]",
    ) as HTMLInputElement
    await act(async () => {
      fireEvent.change(composerFileInput, { target: { files: [draftFile] } })
    })
    await waitFor(() => {
      expect(
        container.querySelectorAll(
          ".shiny-chat-composer .shiny-chat-input-thumbnail",
        ),
      ).toHaveLength(1)
    })

    fireEvent.click(screen.getByRole("button", { name: /next version/i }))

    const navigationCalls = vi.mocked(transport.sendMessageNavigate).mock.calls
    const requestId = navigationCalls[0]?.[3]
    expect(requestId).toEqual(expect.any(String))
    expect(
      screen.getByRole("button", { name: /send message/i }),
    ).toHaveProperty("disabled", true)
    expect(
      screen.getByRole("button", { name: /next version/i }),
    ).toHaveProperty("disabled", true)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
        transition_protocol: "completion-v2",
      })
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: "stale",
      })
    })
    expect(
      screen.getByRole("button", { name: /send message/i }),
    ).toHaveProperty("disabled", true)

    await act(async () => {
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: requestId as string,
      })
    })

    expect(
      screen.getByRole("button", { name: /send message/i }),
    ).toHaveProperty("disabled", false)
    expect(composer).toHaveValue("preserved draft")
    expect(
      container.querySelectorAll(
        ".shiny-chat-composer .shiny-chat-input-thumbnail",
      ),
    ).toHaveLength(1)
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

describe("ChatApp integration: page-owned history presentation", () => {
  let historyChatCount = 0

  function renderHistoryChat({
    pageHistory = true,
    showHistory = true,
    sidebarContent,
  }: {
    pageHistory?: boolean
    showHistory?: boolean
    sidebarContent?: (elementId: string) => string
  } = {}) {
    const transport = createMockTransport()
    const page = document.createElement("shiny-chat-page")
    const chat = document.createElement("shiny-chat-container")
    const elementId = `${pageHistory ? "page-history-chat" : "standalone-history-chat"}-${historyChatCount++}`
    chat.id = elementId
    const defaultSidebarContent = pageHistory
      ? `<shiny-chat-history for="${elementId}"></shiny-chat-history>`
      : ""
    page.innerHTML = `
      <aside class="shiny-chat-page-sidebar">
        ${sidebarContent?.(elementId) ?? defaultSidebarContent}
      </aside>
    `
    page.append(chat)
    document.body.append(page)
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId={elementId}
        inputId="test-input"
        uploadAccept={[]}
        maxUploadSize={null}
        showHistory={showHistory}
      />,
      { container: chat },
    )
    return { transport, page, elementId }
  }

  it("suppresses the embedded trigger when the page sidebar owns history", async () => {
    mockMatchMedia(false)
    const { transport, page, elementId } = renderHistoryChat()

    await act(async () => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(page.querySelector(".shiny-chat-history-trigger")).toBeNull()
  })

  it("retains the embedded trigger when the page has no history sidebar", async () => {
    mockMatchMedia(false)
    const { transport, page, elementId } = renderHistoryChat({
      pageHistory: false,
    })

    await act(async () => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(page.querySelector(".shiny-chat-history-trigger")).not.toBeNull()
  })

  it("ignores history sidebars belonging to inactive navigation pages", async () => {
    mockMatchMedia(false)
    const { transport, page, elementId } = renderHistoryChat({
      pageHistory: false,
      sidebarContent: (historyId) => `
        <div class="shiny-chat-page-sidebar-panel" data-sidebar-for="home"></div>
        <div class="shiny-chat-page-sidebar-panel" data-sidebar-for="sources" hidden>
          <shiny-chat-history for="${historyId}"></shiny-chat-history>
        </div>
      `,
    })
    await act(async () => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(page.querySelector(".shiny-chat-history-trigger")).not.toBeNull()
  })

  it("suppresses the embedded trigger for the active navigation sidebar", async () => {
    mockMatchMedia(false)
    const { transport, page, elementId } = renderHistoryChat({
      pageHistory: false,
      sidebarContent: (historyId) => `
        <div class="shiny-chat-page-sidebar-panel" data-sidebar-for="home">
          <shiny-chat-history for="${historyId}"></shiny-chat-history>
        </div>
        <div class="shiny-chat-page-sidebar-panel" data-sidebar-for="sources" hidden>
          <shiny-chat-history for="another-chat"></shiny-chat-history>
        </div>
      `,
    })
    expect(
      page.querySelector<HTMLElement>(`shiny-chat-history[for="${elementId}"]`),
    ).not.toBeNull()
    expect(
      page
        .querySelector<HTMLElement>(`shiny-chat-history[for="${elementId}"]`)
        ?.closest<HTMLElement>(".shiny-chat-page-sidebar-panel")?.hidden,
    ).toBe(false)
    expect(document.getElementById(elementId)?.closest("shiny-chat-page")).toBe(
      page,
    )
    expect(
      page.querySelectorAll(
        `aside.shiny-chat-page-sidebar shiny-chat-history[for="${elementId}"]`,
      ),
    ).toHaveLength(1)

    await act(async () => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(page.querySelector(".shiny-chat-history-trigger")).toBeNull()
  })

  it("suppresses embedded history when the server disables it", async () => {
    mockMatchMedia(false)
    const { transport, page, elementId } = renderHistoryChat({
      pageHistory: false,
      showHistory: false,
    })

    await act(async () => {
      transport.fire(elementId, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
    })

    expect(page.querySelector(".shiny-chat-history-trigger")).toBeNull()
  })
})

describe("ChatApp integration: streaming smoothing", () => {
  it("does not render chunk text before a pacing tick elapses", async () => {
    vi.useFakeTimers()
    try {
      const transport = createMockTransport()
      const shinyLifecycle = createMockShinyLifecycle()

      render(
        <ChatApp
          transport={transport}
          shinyLifecycle={shinyLifecycle}
          elementId="test-chat"
          inputId="test-input"
          uploadAccept={["image/png"]}
          maxUploadSize={30000000}
          placeholder="Type..."
        />,
      )

      act(() => {
        transport.fire("test-chat", {
          type: "chunk_start",
          message: {
            role: "assistant",
            segments: [{ content: "", content_type: "markdown" }],
          },
        })
      })

      act(() => {
        transport.fire("test-chat", {
          type: "chunk",
          content: "Hello world, this is a longer streamed sentence",
          operation: "append",
        })
      })

      expect(screen.queryByText(/Hello world/)).toBeNull()

      act(() => {
        vi.advanceTimersByTime(500)
      })

      expect(screen.getByText(/Hello world/)).toBeTruthy()

      act(() => {
        transport.fire("test-chat", { type: "chunk_end" })
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it("flushes buffered text before a block_insert so ordering is preserved", async () => {
    vi.useFakeTimers()
    try {
      const transport = createMockTransport()
      const shinyLifecycle = createMockShinyLifecycle()

      render(
        <ChatApp
          transport={transport}
          shinyLifecycle={shinyLifecycle}
          elementId="test-chat"
          inputId="test-input"
          uploadAccept={["image/png"]}
          maxUploadSize={30000000}
          placeholder="Type..."
        />,
      )

      act(() => {
        transport.fire("test-chat", {
          type: "chunk_start",
          message: {
            role: "assistant",
            segments: [{ content: "", content_type: "markdown" }],
          },
        })
      })

      act(() => {
        transport.fire("test-chat", {
          type: "chunk",
          content: "before the block",
          operation: "append",
        })
      })

      // No tick has elapsed yet — the text is still buffered.
      expect(screen.queryByText(/before the block/)).toBeNull()

      act(() => {
        transport.fire("test-chat", {
          type: "block_insert",
          block: { type: "html_block", version: 1, content: "<p>a block</p>" },
        })
      })

      // The block_insert must flush the buffered text first, so it appears
      // even though no timer has elapsed.
      expect(screen.getByText(/before the block/)).toBeTruthy()

      act(() => {
        transport.fire("test-chat", { type: "chunk_end" })
      })
    } finally {
      vi.useRealTimers()
    }
  })
})

describe("ChatApp integration: end-of-stream drain", () => {
  const TAIL = Array.from({ length: 60 }, (_, i) => `w${i}`).join(" ")

  function renderChat(props: Partial<Parameters<typeof ChatApp>[0]> = {}) {
    const transport = createMockTransport()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={["image/png"]}
        maxUploadSize={30000000}
        placeholder="Type..."
        {...props}
      />,
    )
    return transport
  }

  function streamThenEnd(
    transport: ReturnType<typeof createMockTransport>,
    content: string,
  ) {
    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "chunk",
        content,
        operation: "append",
      })
    })
    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })
  }

  const shownText = () =>
    Array.from(document.querySelectorAll(".shiny-chat-message-content"))
      .map((el) => el.textContent ?? "")
      .join("\n")

  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it("reveals the buffered tail over a short window instead of all at once", () => {
    const transport = renderChat()
    streamThenEnd(transport, TAIL)

    // Nothing paced out yet: chunk_end did not dump the buffer.
    expect(shownText()).not.toContain("w59")

    act(() => {
      vi.advanceTimersByTime(100)
    })
    expect(shownText()).toContain("w0")
    expect(shownText()).not.toContain("w59")

    act(() => {
      vi.advanceTimersByTime(500)
    })
    expect(shownText()).toContain(TAIL)
  })

  it("defers unrelated actions until the tail has drained, preserving order", () => {
    const transport = renderChat()
    streamThenEnd(transport, TAIL)

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        placeholder: "Ask a follow-up",
      })
    })
    const textbox = screen.getByRole("textbox", { name: "Chat message" })
    expect(textbox.getAttribute("placeholder")).toBe("Type...")

    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(shownText()).toContain(TAIL)
    expect(textbox.getAttribute("placeholder")).toBe("Ask a follow-up")
  })

  it("completes the drain immediately when a new stream starts", () => {
    const transport = renderChat()
    streamThenEnd(transport, TAIL)

    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })

    expect(shownText()).toContain(TAIL)
  })

  it("Stop during the drain reveals the rest without marking the reply cancelled", () => {
    const transport = renderChat({ cancelId: "test-chat_cancel" })
    act(() => {
      transport.fire("test-chat", {
        type: "update_cancel",
        enable_cancel: true,
      })
    })
    streamThenEnd(transport, TAIL)

    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }))

    expect(shownText()).toContain(TAIL)
    expect(document.querySelector(".shiny-chat-message-cancelled")).toBeNull()

    // No stale cancel flag leaks into the next reply.
    streamThenEnd(transport, "second reply")
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(shownText()).toContain("second reply")
    expect(document.querySelector(".shiny-chat-message-cancelled")).toBeNull()
  })

  it("chunks arriving after Stop are appended immediately, not paced in", () => {
    const transport = renderChat({ cancelId: "test-chat_cancel" })
    act(() => {
      transport.fire("test-chat", {
        type: "update_cancel",
        enable_cancel: true,
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "before stop",
        operation: "append",
      })
    })

    fireEvent.click(screen.getByRole("button", { name: "Stop generating" }))
    // Cancel flushes whatever was still buffered.
    expect(shownText()).toContain("before stop")

    // Providers can over-send after cancellation; those chunks must appear
    // at once rather than keep "typing" in at pacing speed.
    act(() => {
      transport.fire("test-chat", {
        type: "chunk",
        content: " after stop",
        operation: "append",
      })
    })
    expect(shownText()).toContain("after stop")
    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    // A fresh stream paces normally again.
    streamThenEnd(transport, "next reply")
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(shownText()).toContain("next reply")
  })
})

describe("ChatApp integration: composer retained until input is accepted", () => {
  function renderChat({ v2 = true } = {}) {
    const transport = createMockTransport()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="test-chat"
        inputId="test-input"
      />,
    )
    if (v2) {
      act(() => {
        transport.fire("test-chat", {
          type: "history_update",
          enabled: true,
          conversations: [],
          active_id: null,
          transition_protocol: "completion-v2",
        })
      })
    }
    const editorEl = screen.getByRole("textbox", {
      name: "Chat message",
    }) as HTMLTextAreaElement
    return { transport, editorEl }
  }

  async function send(editorEl: HTMLTextAreaElement, text = "my message") {
    await act(async () => {
      fireEvent.change(editorEl, { target: { value: text } })
      fireEvent.keyDown(editorEl, { code: "Enter", key: "Enter" })
    })
  }

  const sentId = (transport: ReturnType<typeof createMockTransport>) =>
    (
      vi.mocked(transport.sendInput).mock.calls[0]![1] as {
        client_message_id: string
      }
    ).client_message_id

  const sentRows = () =>
    screen.queryAllByText("my message", { selector: "p" }).length

  it("keeps the sent text in the locked composer, not the chat, until the server accepts it", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)
    expect(editorEl.value).toBe("my message")
    expect(editorEl.readOnly).toBe(true)
    expect(sentRows()).toBe(0)

    act(() => {
      transport.fire("test-chat", {
        type: "input_received",
        id: sentId(transport),
      })
    })

    // The text moves from the composer into the chat in one step.
    expect(editorEl.value).toBe("")
    expect(editorEl.readOnly).toBe(false)
    expect(sentRows()).toBe(1)
  })

  it("keeps the text and never shows a row when the server rejects the input", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", {
        type: "input_rejected",
        id: sentId(transport),
      })
    })

    expect(editorEl.value).toBe("my message")
    expect(editorEl.readOnly).toBe(false)
    expect(sentRows()).toBe(0)
  })

  it("ignores an acknowledgement for a different input", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", { type: "input_received", id: "other" })
    })

    expect(editorEl.value).toBe("my message")
    expect(editorEl.readOnly).toBe(true)
  })

  it("unlocks without clearing when the server cleans up with remove_loading", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", { type: "remove_loading" })
    })

    expect(editorEl.value).toBe("my message")
    expect(editorEl.readOnly).toBe(false)
  })

  it("holds programmatic input updates until the message is accepted, then applies them in order", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", { type: "update_input", value: "first" })
      transport.fire("test-chat", { type: "update_input", value: "second" })
    })
    expect(editorEl.value).toBe("my message")

    act(() => {
      transport.fire("test-chat", {
        type: "input_received",
        id: sentId(transport),
      })
    })

    // As if the composer had cleared on submit and the updates landed after.
    expect(editorEl.value).toBe("second")
    expect(sentRows()).toBe(1)
  })

  it("refuses a held programmatic submit after acceptance while the response is pending", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "server text",
        submit: true,
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "input_received",
        id: sentId(transport),
      })
    })

    // Same as a programmatic submit arriving mid-response without the hold.
    expect(transport.sendInput).toHaveBeenCalledTimes(1)
    expect(editorEl.value).toBe("")
    expect(screen.queryByText("server text", { selector: "p" })).toBeNull()
  })

  it("discards held programmatic input updates when the message is rejected", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "server text",
        submit: true,
      })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "input_rejected",
        id: sentId(transport),
      })
    })

    expect(editorEl.value).toBe("my message")
    expect(editorEl.readOnly).toBe(false)
    expect(transport.sendInput).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalledWith(
      expect.stringContaining("Discarded input updates"),
    )

    // Updates after the rejection apply normally.
    act(() => {
      transport.fire("test-chat", { type: "update_input", value: "later" })
    })
    expect(editorEl.value).toBe("later")
    warn.mockRestore()
  })

  it.each(["remove_loading", "clear"] as const)(
    "discards held programmatic input updates when %s releases the hold without acceptance",
    async (type) => {
      const { transport, editorEl } = renderChat()
      await send(editorEl)
      const warn = vi.spyOn(console, "warn").mockImplementation(() => {})

      act(() => {
        transport.fire("test-chat", {
          type: "update_input",
          value: "server text",
          submit: true,
        })
      })
      act(() => {
        transport.fire("test-chat", { type })
      })

      // The server never accepted the input, e.g. it failed before commit,
      // so the user's unsent text survives as it does after a rejection.
      expect(editorEl.value).toBe("my message")
      expect(editorEl.readOnly).toBe(false)
      expect(transport.sendInput).toHaveBeenCalledTimes(1)
      expect(warn).toHaveBeenCalledWith(
        expect.stringContaining("Discarded input updates"),
      )
      warn.mockRestore()
    },
  )

  it("keeps held programmatic input updates when remove_loading follows acceptance", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "server text",
      })
      // Same act: nothing commits until all three have been handled.
      transport.fire("test-chat", {
        type: "input_received",
        id: sentId(transport),
      })
      transport.fire("test-chat", { type: "remove_loading" })
    })

    expect(editorEl.value).toBe("server text")
    expect(sentRows()).toBe(1)
  })

  it("applies updates arriving just after acceptance behind the held ones", async () => {
    const { transport, editorEl } = renderChat()
    await send(editorEl)

    act(() => {
      transport.fire("test-chat", { type: "update_input", value: "held" })
      transport.fire("test-chat", {
        type: "input_received",
        id: sentId(transport),
      })
      transport.fire("test-chat", { type: "update_input", value: "after" })
    })

    expect(editorEl.value).toBe("after")
  })

  it("leaves a draft alone when a programmatic submit is accepted", async () => {
    const { transport, editorEl } = renderChat()
    await act(async () => {
      fireEvent.change(editorEl, { target: { value: "my draft" } })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "suggested",
        submit: true,
      })
    })
    const id = sentId(transport)
    expect(editorEl.value).toBe("my draft")

    act(() => {
      transport.fire("test-chat", { type: "input_received", id })
    })
    expect(editorEl.value).toBe("my draft")
    expect(screen.getAllByText("suggested", { selector: "p" })).toHaveLength(1)
  })

  it("leaves a draft alone when a programmatic submit is rejected", async () => {
    const { transport, editorEl } = renderChat()
    await act(async () => {
      fireEvent.change(editorEl, { target: { value: "my draft" } })
    })
    act(() => {
      transport.fire("test-chat", {
        type: "update_input",
        value: "suggested",
        submit: true,
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "input_rejected",
        id: sentId(transport),
      })
    })

    expect(editorEl.value).toBe("my draft")
    expect(screen.queryByText("suggested", { selector: "p" })).toBeNull()
  })

  it("clears immediately and never locks without completion-v2", async () => {
    const { editorEl } = renderChat({ v2: false })
    await send(editorEl)

    expect(editorEl.value).toBe("")
    expect(editorEl.readOnly).toBe(false)
  })
})
