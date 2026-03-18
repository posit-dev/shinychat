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
    onMessage: vi.fn(() => () => {}),
  }
}

function renderChatInput(
  props: Partial<{
    inputId: string
    disabled: boolean
    placeholder: string
    onSend: () => void
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
})
