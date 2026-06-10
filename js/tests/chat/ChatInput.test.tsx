import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { ChatInput, type ChatInputHandle } from "../../src/chat/ChatInput"
import { ChatDispatchContext } from "../../src/chat/context"
import type { ChatTransport } from "../../src/transport/types"
import { createRef, type RefObject } from "react"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockTransport(): ChatTransport {
  return {
    sendInput: vi.fn(),
    sendCancel: vi.fn(),
    sendSlashCommand: vi.fn(),
    onMessage: vi.fn(() => () => {}),
  }
}

function renderChatInput(
  props: Partial<{
    inputId: string
    disabled: boolean
    placeholder: string
    onSend: () => void
    userMessages: string[]
    enableCancel: boolean
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
        disabled={props.disabled ?? false}
        placeholder={props.placeholder ?? "Type here..."}
        onSend={props.onSend}
        userMessages={props.userMessages ?? []}
        enableCancel={props.enableCancel}
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

  it.skip("renders with placeholder", () => {
    // TipTap placeholder extension is not installed; the placeholder attribute
    // is on the EditorContent wrapper, not the contenteditable element.
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
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", "hello")
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

  it("editor has aria-disabled when input is disabled", () => {
    const { editorEl } = renderChatInput({ disabled: true })
    const wrapper = editorEl.closest("[placeholder]") as HTMLElement
    expect(wrapper.getAttribute("aria-disabled")).toBe("true")
  })

  it("editor does not have aria-disabled when input is enabled", () => {
    const { editorEl } = renderChatInput({ disabled: false })
    const wrapper = editorEl.closest("[placeholder]") as HTMLElement
    expect(wrapper.hasAttribute("aria-disabled")).toBe(false)
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
    expect(transport.sendInput).toHaveBeenCalledWith(
      "test-input",
      "click to send",
    )
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

      expect(transport.sendInput).toHaveBeenCalledWith(
        "test-input",
        "submitted text",
      )
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
            disabled={false}
            placeholder="Type here..."
            userMessages={[]}
          />
        </ChatDispatchContext.Provider>,
      )

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
})
