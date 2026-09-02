import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, screen, act, fireEvent, waitFor } from "@testing-library/react"
import { StrictMode } from "react"
import { ChatApp } from "../../src/chat/ChatApp"
import { getHistoryStore } from "../../src/chat/historyStore"
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
  function renderChatApp(
    transport: ReturnType<typeof createMockTransport>,
    enableUpload?: boolean,
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

  it("projects a matching v2 edit through normal input without consuming the composer draft", async () => {
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
      })
      transport.fire("test-chat", {
        type: "history_transition_complete",
        requestId: requestId as string,
      })
    })

    expect(transport.sendInput).toHaveBeenCalledTimes(1)
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
      text: "replacement",
      attachments: replacementAttachments,
    })
    expect(screen.getByRole("button", { name: "Loading" })).toHaveAttribute(
      "aria-disabled",
      "true",
    )
    expect(screen.getByText("custom prefix")).toBeTruthy()
    expect(screen.queryByText("replace me")).toBeNull()
    expect(screen.queryByText("abandoned reply")).toBeNull()
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

  it("sends projected attachments when composer uploads are disabled", async () => {
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
      })
    })

    expect(transport.sendInput).toHaveBeenCalledTimes(1)
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
      text: "replacement",
      attachments: replacementAttachments,
    })
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
        data: { 0: { status: "error", retryable: true } },
      })
    })

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
      expect(transport.sendInput).toHaveBeenCalledWith(
        "test-input",
        "ordinary input",
      )

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
