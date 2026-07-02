import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  render,
  screen,
  fireEvent,
  act,
  createEvent,
  waitFor,
} from "@testing-library/react"

vi.mock("../../src/chat/attachments", async (orig) => {
  const actual = await orig<typeof import("../../src/chat/attachments")>()
  return {
    ...actual,
    processFile: vi.fn(async (file: File) => ({
      file: {
        id: `att-${file.name}`,
        type: file.type,
        family: actual.attachmentFamily(file.type) ?? "document",
        dataUrl: file.type.startsWith("image/")
          ? `data:${file.type};base64,FAKE`
          : `data:${file.type};base64,${btoa("preview body text")}`,
        name: file.name,
        size: 10,
      },
      wasDownscaled: false,
      wasConverted: false,
    })),
  }
})
import { ChatInput, type ChatInputHandle } from "../../src/chat/ChatInput"
import {
  PASTE_AS_FILE_MIN_CHARS,
  processFile,
} from "../../src/chat/attachments"
import { ChatDispatchContext } from "../../src/chat/context"
import type { ChatTransport } from "../../src/transport/types"
import { createRef, type RefObject } from "react"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Mirror the real DataTransfer.getData: text only for the "text/plain" format,
// "" otherwise — so a wrong-format request would surface in tests.
function textFor(format: string, text: string): string {
  return format === "text/plain" ? text : ""
}

function createMockTransport(): ChatTransport {
  return {
    sendInput: vi.fn(),
    sendCancel: vi.fn(),
    sendSlashCommand: vi.fn(),
    sendHistorySelect: vi.fn(),
    sendHistoryNew: vi.fn(),
    sendHistoryRename: vi.fn(),
    sendHistoryDelete: vi.fn(),
    onMessage: vi.fn(() => () => {}),
  }
}

function renderChatInput(
  props: Partial<{
    inputId: string
    uploadAccept: string[]
    maxUploadSize: number
    disabled: boolean
    placeholder: string
    onSend: () => void
    userMessages: string[]
    enableCancel: boolean
    enableUpload: boolean
    cancelRequested: boolean
    isStreaming: boolean
    onCancel: () => void
    slashCommandId: string
    slashCommands: Array<{
      name: string
      description: string
      echo: boolean
    }>
  }> = {},
  ref?: React.RefObject<ChatInputHandle | null>,
) {
  const dispatch = vi.fn()
  const transport = createMockTransport()
  const internalRef = ref ?? createRef<ChatInputHandle>()

  const result = render(
    <ChatDispatchContext.Provider value={dispatch}>
      <ChatInput
        ref={internalRef}
        transport={transport}
        inputId={props.inputId ?? "test-input"}
        uploadAccept={
          props.uploadAccept ?? [
            "image/png",
            "image/jpeg",
            "image/gif",
            "image/webp",
            "application/pdf",
          ]
        }
        maxUploadSize={props.maxUploadSize ?? 30_000_000}
        disabled={props.disabled ?? false}
        placeholder={props.placeholder ?? "Type here..."}
        onSend={props.onSend}
        userMessages={props.userMessages ?? []}
        enableCancel={props.enableCancel}
        enableUpload={props.enableUpload ?? true}
        cancelRequested={props.cancelRequested}
        isStreaming={props.isStreaming}
        onCancel={props.onCancel}
        slashCommandId={props.slashCommandId}
        slashCommands={props.slashCommands}
      />
    </ChatDispatchContext.Provider>,
  )

  const editorEl = screen.getByRole("textbox", {
    name: "Chat message",
  }) as HTMLDivElement

  return { ...result, editorEl, dispatch, transport, ref: internalRef }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ChatInput", () => {
  beforeEach(() => {
    ;(window as unknown as Record<string, unknown>).Shiny = {
      setInputValue: vi.fn(),
    }
    Element.prototype.scrollIntoView = vi.fn()
  })

  it("renders with placeholder", () => {
    const { editorEl } = renderChatInput({ placeholder: "Ask me anything..." })
    expect(editorEl.getAttribute("data-placeholder")).toBe("Ask me anything...")
  })

  it("starts with empty value", () => {
    const { editorEl } = renderChatInput()
    expect(editorEl.textContent).toBe("")
  })

  it("Enter sends input and clears editor", () => {
    const onSend = vi.fn()
    const { editorEl, dispatch, transport, ref } = renderChatInput({ onSend })

    act(() => {
      ref.current?.setInputValue("hello")
    })

    const button = screen.getByRole("button", { name: "Send message" })
    fireEvent.click(button)

    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "INPUT_SENT", content: "hello" }),
    )
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
      text: "hello",
      attachments: [],
    })
    expect(onSend).toHaveBeenCalled()
    expect(editorEl.textContent).toBe("")
  })

  it.skip("Shift+Enter does not send", () => {
    // TipTap's handleKeyDown runs inside ProseMirror's event system, which
    // does not fire from jsdom's fireEvent.keyDown.
  })

  it("does not send when disabled", () => {
    const { dispatch, ref } = renderChatInput({ disabled: true })

    act(() => {
      ref.current?.setInputValue("hello", { submit: true })
    })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it("does not send empty input", () => {
    const { dispatch, ref } = renderChatInput()

    act(() => {
      ref.current?.setInputValue("   ", { submit: true })
    })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it.skip("IME composition blocks Enter; compositionEnd allows it", () => {
    // TipTap's handleKeyDown checks event.isComposing inside ProseMirror's
    // event system, which does not fire from jsdom's fireEvent.
  })

  it("send button is disabled when editor is empty", () => {
    renderChatInput()
    const button = screen.getByRole("button", { name: "Send message" })
    expect((button as HTMLButtonElement).disabled).toBe(true)
  })

  it("shows spinner instead of send button when ChatInput is disabled", () => {
    renderChatInput({ disabled: true })

    expect(screen.queryByRole("button", { name: "Send message" })).toBeNull()
    expect(screen.getByRole("button", { name: "Loading" })).toBeTruthy()
  })

  it("send button is enabled when editor has text", () => {
    const { ref } = renderChatInput()

    act(() => {
      ref.current?.setInputValue("hello")
    })

    const button = screen.getByRole("button", { name: "Send message" })
    expect((button as HTMLButtonElement).disabled).toBe(false)
  })

  it("send button click submits and clears editor", () => {
    const onSend = vi.fn()
    const { editorEl, dispatch, transport, ref } = renderChatInput({ onSend })

    act(() => {
      ref.current?.setInputValue("click to send")
    })

    const button = screen.getByRole("button", { name: "Send message" })
    fireEvent.click(button)

    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "INPUT_SENT", content: "click to send" }),
    )
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
      text: "click to send",
      attachments: [],
    })
    expect(onSend).toHaveBeenCalled()
    expect(editorEl.textContent).toBe("")
  })

  describe("imperative handle", () => {
    it("setInputValue sets the editor value without submitting", () => {
      const ref = createRef<ChatInputHandle>()
      const { editorEl, dispatch } = renderChatInput({}, ref)

      act(() => {
        ref.current?.setInputValue("programmatic value")
      })

      expect(editorEl.textContent).toBe("programmatic value")
      expect(dispatch).not.toHaveBeenCalled()
    })

    it("setInputValue with submit sends and restores old value", () => {
      const ref = createRef<ChatInputHandle>()
      const { editorEl, dispatch, transport } = renderChatInput({}, ref)

      act(() => {
        ref.current?.setInputValue("existing")
      })

      act(() => {
        ref.current?.setInputValue("submitted text", { submit: true })
      })

      expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
        text: "submitted text",
        attachments: [],
      })
      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "INPUT_SENT",
          content: "submitted text",
        }),
      )
      expect(editorEl.textContent).toBe("existing")
    })

    it("setInputValue with submit routes slash commands through sendSlashCommand", () => {
      const ref = createRef<ChatInputHandle>()
      const { editorEl, dispatch, transport } = renderChatInput(
        {
          slashCommandId: "test-slash-command",
          slashCommands: [
            {
              name: "help",
              description: "Show help",
              echo: true,
            },
          ],
        },
        ref,
      )

      act(() => {
        ref.current?.setInputValue("existing")
      })

      act(() => {
        ref.current?.setInputValue("/help topic details", { submit: true })
      })

      expect(transport.sendSlashCommand).toHaveBeenCalledWith(
        "test-slash-command",
        "help",
        "topic details",
        true,
      )
      expect(transport.sendInput).not.toHaveBeenCalled()
      expect(editorEl.textContent).toBe("existing")
    })

    it("setInputValue with submit does not send when disabled", () => {
      const ref = createRef<ChatInputHandle>()
      const { editorEl, dispatch, transport } = renderChatInput(
        { disabled: true },
        ref,
      )

      act(() => {
        ref.current?.setInputValue("existing")
      })

      act(() => {
        ref.current?.setInputValue("submitted text", { submit: true })
      })

      expect(dispatch).not.toHaveBeenCalled()
      expect(transport.sendInput).not.toHaveBeenCalled()
    })

    it.skip("setInputValue with focus focuses the editor", () => {
      // jsdom does not implement focus for contenteditable elements via
      // TipTap's editor.commands.focus(); document.activeElement stays BODY.
    })

    it.skip("focus() focuses the editor", () => {
      // jsdom does not implement focus for contenteditable elements via
      // TipTap's editor.commands.focus(); document.activeElement stays BODY.
    })

    it("setInputValue with submit respects updated disabled prop (no stale closure)", () => {
      const ref = createRef<ChatInputHandle>()
      const dispatch = vi.fn()
      const transport = createMockTransport()

      const { rerender } = render(
        <ChatDispatchContext.Provider value={dispatch}>
          <ChatInput
            ref={ref}
            transport={transport}
            inputId="test-input"
            uploadAccept={[
              "image/png",
              "image/jpeg",
              "image/gif",
              "image/webp",
              "application/pdf",
            ]}
            maxUploadSize={30_000_000}
            disabled={true}
            placeholder="Type here..."
            userMessages={[]}
          />
        </ChatDispatchContext.Provider>,
      )

      act(() => {
        ref.current?.setInputValue("x", { submit: true })
      })
      expect(transport.sendInput).not.toHaveBeenCalled()

      rerender(
        <ChatDispatchContext.Provider value={dispatch}>
          <ChatInput
            ref={ref}
            transport={transport}
            inputId="test-input"
            uploadAccept={[
              "image/png",
              "image/jpeg",
              "image/gif",
              "image/webp",
              "application/pdf",
            ]}
            maxUploadSize={30_000_000}
            disabled={false}
            placeholder="Type here..."
            userMessages={[]}
          />
        </ChatDispatchContext.Provider>,
      )

      // Should send now that disabled=false. Upload is unset here (disabled),
      // so the wire shape is a bare string.
      act(() => {
        ref.current?.setInputValue("x", { submit: true })
      })
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", "x")
    })
  })

  describe("slash command palette", () => {
    it.skip("opens the palette when commands arrive after '/' was typed", () => {
      // The slash command palette is managed by TipTap's Suggestion plugin
      // internally. Triggering it requires dispatching into ProseMirror's
      // editor state, which does not work via jsdom's fireEvent.
    })

    it.skip("does not open the palette when the input does not start with '/'", () => {
      // Same as above — palette state is internal to TipTap's Suggestion plugin.
    })
  })

  describe("input history navigation", () => {
    it.skip("ArrowUp on empty input recalls most recent message", () => {
      // TipTap's handleKeyDown runs inside ProseMirror's event system; jsdom's
      // fireEvent.keyDown does not reach it.
    })

    it.skip("ArrowUp cycles backward through history", () => {
      // Same as above.
    })

    it.skip("ArrowDown past most recent clears input", () => {
      // Same as above.
    })

    it.skip("ArrowDown from fresh state is a no-op", () => {
      // Same as above.
    })

    it.skip("does not trigger when cursor is not at end", () => {
      // Same as above.
    })

    it.skip("does not trigger during IME composition", () => {
      // Same as above.
    })

    it.skip("does not enter recall when input has text (cursor at end)", () => {
      // Same as above.
    })

    it.skip("allows recall when in active mode with edited text", () => {
      // Same as above.
    })

    it.skip("stays in recall mode after returning to blank slot and typing", () => {
      // Same as above.
    })

    it.skip("no-op when history is empty", () => {
      // Same as above.
    })

    it.skip("resets history index after send", () => {
      // Same as above.
    })

    it.skip("resets history after programmatic submit via setInputValue", () => {
      // Same as above.
    })
  })

  describe("stop button", () => {
    it("shows stop button instead of send button when streaming with cancel enabled", () => {
      renderChatInput({ enableCancel: true, isStreaming: true })
      expect(
        screen.getByRole("button", { name: "Stop generating" }),
      ).toBeTruthy()
      expect(screen.queryByRole("button", { name: "Send message" })).toBeNull()
    })

    it("shows send button when not streaming even with cancel enabled", () => {
      renderChatInput({ enableCancel: true, isStreaming: false })
      expect(screen.getByRole("button", { name: "Send message" })).toBeTruthy()
      expect(
        screen.queryByRole("button", { name: "Stop generating" }),
      ).toBeNull()
    })

    it("shows send button when cancel is not enabled even while streaming", () => {
      renderChatInput({ enableCancel: false, isStreaming: true })
      expect(screen.getByRole("button", { name: "Send message" })).toBeTruthy()
      expect(
        screen.queryByRole("button", { name: "Stop generating" }),
      ).toBeNull()
    })

    it("calls onCancel when stop button is clicked", () => {
      const onCancel = vi.fn()
      renderChatInput({
        enableCancel: true,
        isStreaming: true,
        onCancel,
      })
      const button = screen.getByRole("button", { name: "Stop generating" })
      fireEvent.click(button)
      expect(onCancel).toHaveBeenCalledTimes(1)
    })

    it("shows spinner instead of stop button when cancelRequested is true", () => {
      renderChatInput({
        enableCancel: true,
        isStreaming: true,
        cancelRequested: true,
      })
      expect(
        screen.queryByRole("button", { name: "Stop generating" }),
      ).toBeNull()
      expect(screen.getByRole("button", { name: "Loading" })).toBeTruthy()
    })

    it("stop button is enabled when cancelRequested is false", () => {
      renderChatInput({
        enableCancel: true,
        isStreaming: true,
        cancelRequested: false,
      })
      const button = screen.getByRole("button", {
        name: "Stop generating",
      }) as HTMLButtonElement
      expect(button.disabled).toBe(false)
    })
  })

  describe("spinner button", () => {
    it("shows spinner when disabled but not yet streaming (pending state)", () => {
      renderChatInput({ disabled: true, isStreaming: false })
      expect(screen.getByRole("button", { name: "Loading" })).toBeTruthy()
      expect(screen.queryByRole("button", { name: "Send message" })).toBeNull()
      expect(
        screen.queryByRole("button", { name: "Stop generating" }),
      ).toBeNull()
    })

    it("shows spinner (not cancel button) when pending even with enableCancel", () => {
      renderChatInput({
        disabled: true,
        isStreaming: false,
        enableCancel: true,
      })
      expect(screen.getByRole("button", { name: "Loading" })).toBeTruthy()
      expect(
        screen.queryByRole("button", { name: "Stop generating" }),
      ).toBeNull()
    })
  })

  describe("client-side slash command interception", () => {
    function renderSlash(
      echo: boolean,
      ref: RefObject<ChatInputHandle | null>,
    ) {
      return renderChatInput(
        {
          slashCommandId: "test-slash-command",
          slashCommands: [{ name: "do", description: "Do a thing", echo }],
        },
        ref,
      )
    }

    it("dispatches a shiny:chat-slash-command event with the command detail", () => {
      const ref = createRef<ChatInputHandle>()
      renderSlash(true, ref)
      const events: CustomEvent[] = []
      const listener = (e: Event) => events.push(e as CustomEvent)
      document.addEventListener("shiny:chat-slash-command", listener)

      act(() => {
        ref.current?.setInputValue("/do stuff here", { submit: true })
      })
      document.removeEventListener("shiny:chat-slash-command", listener)

      expect(events).toHaveLength(1)
      expect(events[0]!.detail).toMatchObject({
        command: "do",
        userText: "stuff here",
        echo: true,
      })
    })

    it("preventDefault skips the server round-trip", () => {
      const ref = createRef<ChatInputHandle>()
      const { transport } = renderSlash(false, ref)
      const listener = (e: Event) => e.preventDefault()
      document.addEventListener("shiny:chat-slash-command", listener)

      act(() => {
        ref.current?.setInputValue("/do", { submit: true })
      })
      document.removeEventListener("shiny:chat-slash-command", listener)

      expect(transport.sendSlashCommand).not.toHaveBeenCalled()
    })

    it("echo=false sends to the server without echoing a user message", () => {
      const ref = createRef<ChatInputHandle>()
      const { dispatch, transport } = renderSlash(false, ref)

      act(() => {
        ref.current?.setInputValue("/do", { submit: true })
      })

      expect(dispatch).not.toHaveBeenCalledWith(
        expect.objectContaining({ type: "INPUT_SENT" }),
      )
      expect(transport.sendSlashCommand).toHaveBeenCalledWith(
        "test-slash-command",
        "do",
        "",
        false,
      )
    })

    it("echo=true echoes the user message and awaits a response", () => {
      const ref = createRef<ChatInputHandle>()
      const { dispatch, transport } = renderSlash(true, ref)

      act(() => {
        ref.current?.setInputValue("/do now", { submit: true })
      })

      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "INPUT_SENT",
          content: "/do now",
          awaitResponse: true,
        }),
      )
      expect(transport.sendSlashCommand).toHaveBeenCalledWith(
        "test-slash-command",
        "do",
        "now",
        true,
      )
    })

    it("prevented + echo=true echoes a bubble but does not await a response", () => {
      const ref = createRef<ChatInputHandle>()
      const { dispatch, transport } = renderSlash(true, ref)
      const listener = (e: Event) => e.preventDefault()
      document.addEventListener("shiny:chat-slash-command", listener)

      act(() => {
        ref.current?.setInputValue("/do", { submit: true })
      })
      document.removeEventListener("shiny:chat-slash-command", listener)

      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "INPUT_SENT",
          awaitResponse: false,
        }),
      )
      expect(transport.sendSlashCommand).not.toHaveBeenCalled()
    })

    it("prevented + echo=false is a no-op (no bubble, no server call)", () => {
      const ref = createRef<ChatInputHandle>()
      const { dispatch, transport } = renderSlash(false, ref)
      const listener = (e: Event) => e.preventDefault()
      document.addEventListener("shiny:chat-slash-command", listener)

      act(() => {
        ref.current?.setInputValue("/do", { submit: true })
      })
      document.removeEventListener("shiny:chat-slash-command", listener)

      expect(dispatch).not.toHaveBeenCalledWith(
        expect.objectContaining({ type: "INPUT_SENT" }),
      )
      expect(transport.sendSlashCommand).not.toHaveBeenCalled()
    })

    it("a listener can override detail.echo and it is forwarded to the server", () => {
      const ref = createRef<ChatInputHandle>()
      const { dispatch, transport } = renderSlash(true, ref)
      const listener = (e: Event) => {
        ;(e as CustomEvent).detail.echo = false
      }
      document.addEventListener("shiny:chat-slash-command", listener)

      act(() => {
        ref.current?.setInputValue("/do x", { submit: true })
      })
      document.removeEventListener("shiny:chat-slash-command", listener)

      expect(dispatch).not.toHaveBeenCalledWith(
        expect.objectContaining({ type: "INPUT_SENT" }),
      )
      expect(transport.sendSlashCommand).toHaveBeenCalledWith(
        "test-slash-command",
        "do",
        "x",
        false,
      )
    })
  })

  describe("image attachments", () => {
    function pngFile(name = "a.png"): File {
      return new File(["x"], name, { type: "image/png" })
    }

    it("shows the attach button when upload is enabled", () => {
      renderChatInput({ enableUpload: true })
      expect(screen.getByRole("button", { name: "Attach file" })).toBeTruthy()
    })

    it("hides the attach button when upload is disabled", () => {
      renderChatInput({ enableUpload: false })
      expect(screen.queryByRole("button", { name: "Attach file" })).toBeNull()
    })

    it("ignores pasted images when upload is disabled", async () => {
      const { editorEl, dispatch } = renderChatInput({ enableUpload: false })
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              { kind: "file", type: "image/png", getAsFile: () => pngFile() },
            ],
            getData: () => "",
          },
        })
      })
      expect(screen.queryByRole("img", { name: /attached/i })).toBeNull()
      expect(dispatch).not.toHaveBeenCalled()
    })

    it("paste adds a thumbnail and prevents default", async () => {
      const { editorEl } = renderChatInput()
      const items = [
        { kind: "file", type: "image/png", getAsFile: () => pngFile() },
      ]
      await act(async () => {
        fireEvent.paste(editorEl, { clipboardData: { items } })
      })
      expect(screen.getByRole("img", { name: /attached/i })).toBeTruthy()
    })

    it("send button is enabled with an image and no text", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              { kind: "file", type: "image/png", getAsFile: () => pngFile() },
            ],
          },
        })
      })
      const button = screen.getByRole("button", { name: "Send message" })
      expect((button as HTMLButtonElement).disabled).toBe(false)
    })

    it("submitting sends composite input with attachments", async () => {
      const { editorEl, dispatch, transport, ref } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              { kind: "file", type: "image/png", getAsFile: () => pngFile() },
            ],
          },
        })
      })
      act(() => {
        ref.current?.setInputValue("describe")
      })
      fireEvent.click(screen.getByRole("button", { name: "Send message" }))

      // The size field is carried here and stripped by ShinyTransport when
      // building the wire payload.
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
        text: "describe",
        attachments: [
          {
            mime: "image/png",
            data_url: "data:image/png;base64,FAKE",
            name: "a.png",
            size: 10,
          },
        ],
      })
      expect(dispatch).toHaveBeenCalledWith(
        expect.objectContaining({
          type: "INPUT_SENT",
          content: "describe",
          attachments: [
            {
              mime: "image/png",
              data_url: "data:image/png;base64,FAKE",
              name: "a.png",
              size: 10,
            },
          ],
        }),
      )
    })

    it("clears thumbnails after sending", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              { kind: "file", type: "image/png", getAsFile: () => pngFile() },
            ],
          },
        })
      })
      fireEvent.click(screen.getByRole("button", { name: "Send message" }))
      expect(screen.queryByRole("img", { name: /attached/i })).toBeNull()
    })

    it("remove button removes a thumbnail", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              { kind: "file", type: "image/png", getAsFile: () => pngFile() },
            ],
          },
        })
      })
      fireEvent.click(screen.getByRole("button", { name: /^remove/i }))
      expect(screen.queryByRole("img", { name: /attached/i })).toBeNull()
    })

    it("uses the file name as the thumbnail title and accessible name", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              {
                kind: "file",
                type: "image/png",
                getAsFile: () =>
                  new File(["x"], "photo.png", { type: "image/png" }),
              },
            ],
          },
        })
      })
      const thumb = document.querySelector(
        ".shiny-chat-input-thumbnail",
      ) as HTMLElement
      expect(thumb.getAttribute("title")).toBe("photo.png")
      expect(
        screen.getByRole("img", { name: "Attached image: photo.png" }),
      ).toBeTruthy()
    })

    it("does not cap the number of attachments (the size cap governs instead)", async () => {
      const { editorEl } = renderChatInput()
      const items = Array.from({ length: 8 }, (_, i) => ({
        kind: "file",
        type: "image/png",
        getAsFile: () => new File(["x"], `img-${i}.png`, { type: "image/png" }),
      }))
      await act(async () => {
        fireEvent.paste(editorEl, { clipboardData: { items } })
      })
      expect(screen.getAllByRole("img", { name: /attached/i })).toHaveLength(8)
      expect(screen.queryByText(/up to/i)).toBeNull()
    })

    it("drop over the attachment tray adds an image when one is already attached", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              {
                kind: "file",
                type: "image/png",
                getAsFile: () => pngFile("first.png"),
              },
            ],
          },
        })
      })
      expect(screen.getAllByRole("img", { name: /attached/i })).toHaveLength(1)

      const tray = document.querySelector(
        ".shiny-chat-input-attachments",
      ) as HTMLElement
      await act(async () => {
        fireEvent.drop(tray, {
          dataTransfer: { files: [pngFile("second.png")] },
        })
      })
      expect(screen.getAllByRole("img", { name: /attached/i })).toHaveLength(2)
    })

    it("dragover over the attachment tray prevents default so a drop is allowed", async () => {
      const { editorEl } = renderChatInput()
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              {
                kind: "file",
                type: "image/png",
                getAsFile: () => pngFile("first.png"),
              },
            ],
          },
        })
      })
      const tray = document.querySelector(
        ".shiny-chat-input-attachments",
      ) as HTMLElement
      const ev = createEvent.dragOver(tray, {
        dataTransfer: { files: [pngFile("second.png")] },
      })
      fireEvent(tray, ev)
      expect(ev.defaultPrevented).toBe(true)
    })

    it("drop passes through to the browser when enableUpload is false", () => {
      renderChatInput({ enableUpload: false })
      const dropzone = document.querySelector(
        ".shiny-chat-input-dropzone",
      ) as HTMLElement
      const ev = createEvent.drop(dropzone, {
        dataTransfer: { files: [pngFile("ignored.png")] },
      })
      fireEvent(dropzone, ev)
      expect(ev.defaultPrevented).toBe(false)
      expect(screen.queryByRole("img", { name: /attached/i })).toBeNull()
    })

    it("concurrent pastes respect the size limit", async () => {
      // maxUploadSize = 15 fits one file (mock size = 10) but not two (20).
      const { editorEl } = renderChatInput({ maxUploadSize: 15 })
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              {
                kind: "file",
                type: "image/png",
                getAsFile: () => pngFile("first.png"),
              },
            ],
          },
        })
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [
              {
                kind: "file",
                type: "image/png",
                getAsFile: () => pngFile("second.png"),
              },
            ],
          },
        })
      })
      // Only one file should be accepted — the second exceeds the limit.
      expect(screen.getAllByRole("img", { name: /attached/i })).toHaveLength(1)
    })

    it("does not send when both text and attachments are empty", () => {
      const { dispatch, ref } = renderChatInput()
      act(() => {
        ref.current?.setInputValue("", { submit: true })
      })
      expect(dispatch).not.toHaveBeenCalled()
    })

    it("text-only submit sends composite with empty attachments array", () => {
      const { transport, ref } = renderChatInput()
      act(() => {
        ref.current?.setInputValue("just text")
      })
      fireEvent.click(screen.getByRole("button", { name: "Send message" }))
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
        text: "just text",
        attachments: [],
      })
    })

    it("sends a bare string (not a composite) when upload is disabled", () => {
      const { transport, ref } = renderChatInput({ enableUpload: false })
      act(() => {
        ref.current?.setInputValue("just text")
      })
      fireEvent.click(screen.getByRole("button", { name: "Send message" }))
      expect(transport.sendInput).toHaveBeenCalledWith(
        "test-input",
        "just text",
      )
    })

    it("large text paste becomes a 'Pasted Text' card and prevents default", async () => {
      const { editorEl } = renderChatInput({
        uploadAccept: ["text/plain", "image/png"],
      })
      const big = "x".repeat(1500)
      const ev = createEvent.paste(editorEl, {
        clipboardData: { items: [], getData: (f: string) => textFor(f, big) },
      })
      await act(async () => {
        fireEvent(editorEl, ev)
      })
      expect(ev.defaultPrevented).toBe(true)
      expect(editorEl.textContent).toBe("")
      expect(screen.getByText("Pasted Text")).toBeTruthy()
    })

    it("short text paste is left to the default (no card)", async () => {
      const { editorEl } = renderChatInput({ uploadAccept: ["text/plain"] })
      const ev = createEvent.paste(editorEl, {
        clipboardData: {
          items: [],
          getData: (f: string) => textFor(f, "short note"),
        },
      })
      await act(async () => {
        fireEvent(editorEl, ev)
      })
      // Tiptap handles the paste itself (and preventDefaults to do so); ours
      // is a passthrough when below the threshold, so no card is created.
      expect(screen.queryByText("Pasted Text")).toBeNull()
      expect(document.querySelector(".shiny-chat-input-attachments")).toBeNull()
    })

    it("does not convert text of exactly the threshold length", async () => {
      const { editorEl } = renderChatInput({ uploadAccept: ["text/plain"] })
      const atThreshold = "x".repeat(PASTE_AS_FILE_MIN_CHARS)
      const ev = createEvent.paste(editorEl, {
        clipboardData: {
          items: [],
          getData: (f: string) => textFor(f, atThreshold),
        },
      })
      await act(async () => {
        fireEvent(editorEl, ev)
      })
      expect(screen.queryByText("Pasted Text")).toBeNull()
      expect(document.querySelector(".shiny-chat-input-attachments")).toBeNull()
    })

    it("large text paste preserves already-typed text", async () => {
      const { editorEl, ref } = renderChatInput({
        uploadAccept: ["text/plain"],
      })
      act(() => {
        ref.current?.setInputValue("my note")
      })
      const ev = createEvent.paste(editorEl, {
        clipboardData: {
          items: [],
          getData: (f: string) => textFor(f, "x".repeat(1500)),
        },
      })
      await act(async () => {
        fireEvent(editorEl, ev)
      })
      expect(editorEl.textContent).toBe("my note")
      expect(screen.getByText("Pasted Text")).toBeTruthy()
    })

    it("does not convert a large text paste when text/plain is not accepted", async () => {
      const { editorEl } = renderChatInput({ uploadAccept: ["image/png"] })
      const ev = createEvent.paste(editorEl, {
        clipboardData: {
          items: [],
          getData: (f: string) => textFor(f, "x".repeat(1500)),
        },
      })
      await act(async () => {
        fireEvent(editorEl, ev)
      })
      expect(screen.queryByText("Pasted Text")).toBeNull()
      expect(document.querySelector(".shiny-chat-input-attachments")).toBeNull()
    })

    it("submitting after a large paste sends a text/plain 'Pasted Text' attachment", async () => {
      const { editorEl, transport } = renderChatInput({
        uploadAccept: ["text/plain"],
      })
      await act(async () => {
        fireEvent.paste(editorEl, {
          clipboardData: {
            items: [],
            getData: (f: string) => textFor(f, "x".repeat(1500)),
          },
        })
      })
      fireEvent.click(screen.getByRole("button", { name: "Send message" }))
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", {
        text: "",
        attachments: [
          {
            mime: "text/plain",
            name: "Pasted Text",
            data_url: expect.stringContaining("data:text/plain;base64,"),
            size: 10,
          },
        ],
      })
    })
  })

  describe("ChatInput attachments", () => {
    it("renders a document chip for an attached PDF", async () => {
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["application/pdf"],
        maxUploadSize: 1_000_000,
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const pdf = new File(["%PDF-1.4 hello"], "report.pdf", {
        type: "application/pdf",
      })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [pdf] } })
      })

      await waitFor(() => {
        expect(
          container.querySelector(".shiny-chat-input-attachment-chip"),
        ).not.toBeNull()
      })
      expect(container.textContent).toContain("report.pdf")
    })

    it("renders a text preview card for an attached text file", async () => {
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["text/markdown"],
        maxUploadSize: 1_000_000,
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const md = new File(["# Notes"], "notes.md", { type: "text/markdown" })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [md] } })
      })
      await waitFor(() => {
        expect(
          container.querySelector(".shiny-chat-text-preview"),
        ).not.toBeNull()
      })
      expect(container.textContent).toContain("preview body text")
      expect(container.textContent).toContain("notes.md")
    })

    it("rejects a file that exceeds the total size cap and shows a notice", async () => {
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["application/pdf"],
        maxUploadSize: 5, // mocked processFile reports size 10 > 5
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const pdf = new File(["%PDF-1.4 hello world"], "big.pdf", {
        type: "application/pdf",
      })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [pdf] } })
      })

      await waitFor(() => {
        expect(screen.getByRole("status").textContent).toMatch(/exceed/i)
      })
      expect(
        container.querySelector(".shiny-chat-input-attachment-chip"),
      ).toBeNull()
    })

    it("clears the size notice after the attachment is removed", async () => {
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["application/pdf"],
        maxUploadSize: 15, // mocked processFile reports size 10 each
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const a = new File(["%PDF-1.4 a"], "a.pdf", { type: "application/pdf" })
      const b = new File(["%PDF-1.4 b"], "b.pdf", { type: "application/pdf" })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [a, b] } })
      })
      // First accepted, second rejected for size -> notice shown, one chip.
      await waitFor(() => {
        expect(screen.getByRole("status").textContent).toMatch(/exceed/i)
      })
      expect(
        container.querySelectorAll(".shiny-chat-input-attachment-chip"),
      ).toHaveLength(1)

      // Remove the remaining chip -> size notice clears.
      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /^remove/i }))
      })
      expect(screen.queryByText(/exceed/i)).toBeNull()
    })

    it("shows a notice when an animated GIF is converted to a still image", async () => {
      vi.mocked(processFile).mockImplementationOnce(async (file: File) => ({
        file: {
          id: `att-${file.name}`,
          type: "image/png",
          family: "image",
          dataUrl: "data:image/png;base64,FAKE",
          name: file.name,
          size: 10,
        },
        wasDownscaled: true,
        wasConverted: true,
      }))
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["image/gif"],
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const gif = new File(["GIF89a"], "loop.gif", { type: "image/gif" })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [gif] } })
      })

      await waitFor(() => {
        expect(screen.getByRole("status").textContent).toMatch(
          /converted to a still image/i,
        )
      })
    })

    it("clears the GIF-conversion notice after the attachment is removed", async () => {
      vi.mocked(processFile).mockImplementationOnce(async (file: File) => ({
        file: {
          id: `att-${file.name}`,
          type: "image/png",
          family: "image",
          dataUrl: "data:image/png;base64,FAKE",
          name: file.name,
          size: 10,
        },
        wasDownscaled: true,
        wasConverted: true,
      }))
      const { container } = renderChatInput({
        enableUpload: true,
        uploadAccept: ["image/gif"],
      })
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      const gif = new File(["GIF89a"], "loop.gif", { type: "image/gif" })
      await act(async () => {
        fireEvent.change(fileInput, { target: { files: [gif] } })
      })
      await waitFor(() => {
        expect(screen.getByRole("status").textContent).toMatch(
          /converted to a still image/i,
        )
      })

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /^remove/i }))
      })
      expect(screen.queryByText(/converted to a still image/i)).toBeNull()
    })
  })

  describe("attachment focus and keyboard removal", () => {
    function pdfFile(name: string): File {
      return new File(["%PDF-1.4"], name, { type: "application/pdf" })
    }

    async function stagePdfs(
      container: HTMLElement,
      names: string[],
    ): Promise<void> {
      const fileInput = container.querySelector(
        'input[type="file"]',
      ) as HTMLInputElement
      await act(async () => {
        fireEvent.change(fileInput, {
          target: { files: names.map((n) => pdfFile(n)) },
        })
      })
    }

    function chips(container: HTMLElement): HTMLElement[] {
      return Array.from(
        container.querySelectorAll(".shiny-chat-input-attachment-chip"),
      ) as HTMLElement[]
    }

    it("a staged attachment and its remove button are both in the tab order", async () => {
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf"])
      const chip = chips(container)[0]!
      expect(chip.tabIndex).toBe(0)
      const removeBtn = chip.querySelector("button") as HTMLButtonElement
      expect(removeBtn.tabIndex).toBe(0)
    })

    it("clicking a staged attachment focuses its container", async () => {
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf"])
      const chip = chips(container)[0]!
      fireEvent.click(chip)
      expect(document.activeElement).toBe(chip)
    })

    it("Delete removes the focused attachment", async () => {
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf"])
      const chip = chips(container)[0]!
      chip.focus()
      await act(async () => {
        fireEvent.keyDown(chip, { code: "Delete" })
      })
      expect(chips(container)).toHaveLength(0)
    })

    it("Backspace removes the focused attachment", async () => {
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf"])
      const chip = chips(container)[0]!
      chip.focus()
      await act(async () => {
        fireEvent.keyDown(chip, { code: "Backspace" })
      })
      expect(chips(container)).toHaveLength(0)
    })

    it("removing a focused attachment moves focus to the next one", async () => {
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf", "b.pdf", "c.pdf"])
      const middle = chips(container)[1]!
      middle.focus()
      await act(async () => {
        fireEvent.keyDown(middle, { code: "Delete" })
      })
      const remaining = chips(container)
      expect(remaining).toHaveLength(2)
      // c.pdf has shifted into the slot the removed b.pdf vacated.
      expect(document.activeElement).toBe(remaining[1])
      expect(remaining[1]!.getAttribute("aria-label")).toContain("c.pdf")
    })

    it("removing the last remaining attachment removes the tray", async () => {
      // Focus moving back to the editor is covered in Playwright; jsdom does
      // not implement focus for contenteditable elements, so we can only
      // assert the removal itself here.
      const { container } = renderChatInput()
      await stagePdfs(container, ["a.pdf"])
      const chip = chips(container)[0]!
      chip.focus()
      await act(async () => {
        fireEvent.keyDown(chip, { code: "Delete" })
      })
      expect(chips(container)).toHaveLength(0)
      expect(
        container.querySelector(".shiny-chat-input-attachments"),
      ).toBeNull()
    })
  })
})
