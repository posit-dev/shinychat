import { describe, it, expect, vi, beforeEach } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { ChatInput, type ChatInputHandle } from "../../src/chat/ChatInput"
import { ChatDispatchContext } from "../../src/chat/context"
import type { ChatTransport } from "../../src/transport/types"
import { createRef } from "react"

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createMockTransport(): ChatTransport {
  return {
    sendInput: vi.fn(),
    sendCancel: vi.fn(),
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
  }> = {},
  ref?: React.RefObject<ChatInputHandle | null>,
) {
  const dispatch = vi.fn()
  const transport = createMockTransport()

  const result = render(
    <ChatDispatchContext.Provider value={dispatch}>
      <ChatInput
        ref={ref ?? null}
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
      />
    </ChatDispatchContext.Provider>,
  )

  const textarea = screen.getByPlaceholderText(
    props.placeholder ?? "Type here...",
  ) as HTMLTextAreaElement

  return { ...result, textarea, dispatch, transport }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("ChatInput", () => {
  beforeEach(() => {
    ;(window as unknown as Record<string, unknown>).Shiny = {
      setInputValue: vi.fn(),
    }
  })

  it("renders with placeholder", () => {
    const { textarea } = renderChatInput({ placeholder: "Ask me anything" })
    expect(textarea.placeholder).toBe("Ask me anything")
  })

  it("starts with empty value", () => {
    const { textarea } = renderChatInput()
    expect(textarea.value).toBe("")
  })

  it("Enter sends input and clears textarea", () => {
    const onSend = vi.fn()
    const { textarea, dispatch, transport } = renderChatInput({ onSend })

    // Type into the textarea
    textarea.value = "hello"
    fireEvent.input(textarea)

    // Press Enter
    fireEvent.keyDown(textarea, { code: "Enter" })

    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "INPUT_SENT", content: "hello" }),
    )
    expect(transport.sendInput).toHaveBeenCalledWith("test-input", "hello")
    expect(onSend).toHaveBeenCalled()
    expect(textarea.value).toBe("")
  })

  it("Shift+Enter does not send", () => {
    const { textarea, dispatch } = renderChatInput()

    textarea.value = "hello"
    fireEvent.input(textarea)

    fireEvent.keyDown(textarea, { code: "Enter", shiftKey: true })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it("does not send when disabled", () => {
    const { textarea, dispatch } = renderChatInput({ disabled: true })

    textarea.value = "hello"
    fireEvent.input(textarea)

    fireEvent.keyDown(textarea, { code: "Enter" })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it("textarea has aria-disabled when input is disabled", () => {
    const { textarea } = renderChatInput({ disabled: true })
    expect(textarea.getAttribute("aria-disabled")).toBe("true")
  })

  it("textarea does not have aria-disabled when input is enabled", () => {
    const { textarea } = renderChatInput({ disabled: false })
    expect(textarea.hasAttribute("aria-disabled")).toBe(false)
  })

  it("does not send empty input", () => {
    const { textarea, dispatch } = renderChatInput()

    textarea.value = "   "
    fireEvent.input(textarea)

    fireEvent.keyDown(textarea, { code: "Enter" })

    expect(dispatch).not.toHaveBeenCalled()
  })

  it("IME composition blocks Enter; compositionEnd allows it", () => {
    const { textarea, dispatch } = renderChatInput()

    textarea.value = "日本語"
    fireEvent.input(textarea)

    // During IME composition, Enter should not submit
    fireEvent.compositionStart(textarea)
    fireEvent.keyDown(textarea, { code: "Enter" })
    expect(dispatch).not.toHaveBeenCalled()

    // After compositionEnd, Enter should submit
    fireEvent.compositionEnd(textarea)
    fireEvent.keyDown(textarea, { code: "Enter" })
    expect(dispatch).toHaveBeenCalledWith(
      expect.objectContaining({ type: "INPUT_SENT", content: "日本語" }),
    )
  })

  it("send button is disabled when textarea is empty", () => {
    renderChatInput()
    const button = screen.getByRole("button", { name: "Send message" })
    expect((button as HTMLButtonElement).disabled).toBe(true)
  })

  it("send button is disabled when ChatInput is disabled", () => {
    const { textarea } = renderChatInput({ disabled: true })

    textarea.value = "hello"
    fireEvent.input(textarea)

    const button = screen.getByRole("button", { name: "Send message" })
    expect((button as HTMLButtonElement).disabled).toBe(true)
  })

  it("send button is enabled when textarea has text", () => {
    const { textarea } = renderChatInput()

    textarea.value = "hello"
    fireEvent.input(textarea)

    const button = screen.getByRole("button", { name: "Send message" })
    expect((button as HTMLButtonElement).disabled).toBe(false)
  })

  it("send button click submits and clears textarea", () => {
    const onSend = vi.fn()
    const { textarea, dispatch, transport } = renderChatInput({ onSend })

    textarea.value = "click to send"
    fireEvent.input(textarea)

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
    expect(textarea.value).toBe("")
  })

  describe("imperative handle", () => {
    it("setInputValue sets the textarea value without submitting", () => {
      const ref = createRef<ChatInputHandle>()
      const { textarea, dispatch } = renderChatInput({}, ref)

      act(() => {
        ref.current?.setInputValue("programmatic value")
      })

      expect(textarea.value).toBe("programmatic value")
      expect(dispatch).not.toHaveBeenCalled()
    })

    it("setInputValue with submit sends and restores old value", () => {
      const ref = createRef<ChatInputHandle>()
      const { textarea, dispatch, transport } = renderChatInput({}, ref)

      // Set an existing value first
      textarea.value = "existing"
      fireEvent.input(textarea)

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
      // Old value restored
      expect(textarea.value).toBe("existing")
    })

    it("setInputValue with submit does not send when disabled", () => {
      const ref = createRef<ChatInputHandle>()
      const { textarea, dispatch, transport } = renderChatInput(
        { disabled: true },
        ref,
      )

      textarea.value = "existing"
      fireEvent.input(textarea)

      act(() => {
        ref.current?.setInputValue("submitted text", { submit: true })
      })

      expect(dispatch).not.toHaveBeenCalled()
      expect(transport.sendInput).not.toHaveBeenCalled()
      // Old value should remain unchanged
      expect(textarea.value).toBe("existing")
    })

    it("setInputValue with focus focuses the textarea", () => {
      const ref = createRef<ChatInputHandle>()
      const { textarea } = renderChatInput({}, ref)

      act(() => {
        ref.current?.setInputValue("focused", { focus: true })
      })

      expect(textarea.value).toBe("focused")
      expect(document.activeElement).toBe(textarea)
    })

    it("focus() focuses the textarea", () => {
      const ref = createRef<ChatInputHandle>()
      const { textarea } = renderChatInput({}, ref)

      act(() => {
        ref.current?.focus()
      })

      expect(document.activeElement).toBe(textarea)
    })

    it("setInputValue with submit respects updated disabled prop (no stale closure)", () => {
      const ref = createRef<ChatInputHandle>()
      const dispatch = vi.fn()
      const transport = createMockTransport()

      // Initial render with disabled=true
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

      // Should NOT send when disabled=true
      act(() => {
        ref.current?.setInputValue("x", { submit: true })
      })
      expect(transport.sendInput).not.toHaveBeenCalled()

      // Re-render with disabled=false
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

      // Should send now that disabled=false
      act(() => {
        ref.current?.setInputValue("x", { submit: true })
      })
      expect(transport.sendInput).toHaveBeenCalledWith("test-input", "x")
    })
  })

  describe("input history navigation", () => {
    const history = ["first", "second", "third"]

    function setCursorAtEnd(textarea: HTMLTextAreaElement): void {
      Object.defineProperty(textarea, "selectionStart", {
        get: () => textarea.value.length,
        configurable: true,
      })
    }

    it("ArrowUp on empty input recalls most recent message", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      fireEvent.keyDown(textarea, { code: "ArrowUp" })

      expect(textarea.value).toBe("third")
    })

    it("ArrowUp cycles backward through history", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("third")

      setCursorAtEnd(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("second")

      setCursorAtEnd(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("first")
    })

    it("ArrowDown past most recent clears input", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("third")

      setCursorAtEnd(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowDown" })
      expect(textarea.value).toBe("")
    })

    it("ArrowDown from fresh state is a no-op", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      fireEvent.keyDown(textarea, { code: "ArrowDown" })

      expect(textarea.value).toBe("")
    })

    it("does not trigger when cursor is not at end", () => {
      const { textarea } = renderChatInput({ userMessages: history })

      textarea.value = "some text"
      fireEvent.input(textarea)
      Object.defineProperty(textarea, "selectionStart", {
        get: () => 4,
        configurable: true,
      })

      fireEvent.keyDown(textarea, { code: "ArrowUp" })

      expect(textarea.value).toBe("some text")
    })

    it("does not trigger during IME composition", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      fireEvent.compositionStart(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowUp" })

      expect(textarea.value).toBe("")
    })

    it("no-op when history is empty", () => {
      const { textarea } = renderChatInput({ userMessages: [] })
      setCursorAtEnd(textarea)

      fireEvent.keyDown(textarea, { code: "ArrowUp" })

      expect(textarea.value).toBe("")
    })

    it("resets history index after send", () => {
      const { textarea } = renderChatInput({ userMessages: history })
      setCursorAtEnd(textarea)

      // Navigate to "second"
      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      setCursorAtEnd(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("second")

      // Send it
      fireEvent.keyDown(textarea, { code: "Enter" })
      expect(textarea.value).toBe("")

      // Next ArrowUp should start from most recent again
      setCursorAtEnd(textarea)
      fireEvent.keyDown(textarea, { code: "ArrowUp" })
      expect(textarea.value).toBe("third")
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

    it("stop button is disabled when cancelRequested is true", () => {
      renderChatInput({
        enableCancel: true,
        isStreaming: true,
        cancelRequested: true,
      })
      const button = screen.getByRole("button", {
        name: "Stop generating",
      }) as HTMLButtonElement
      expect(button.disabled).toBe(true)
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
})
