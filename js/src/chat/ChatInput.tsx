import {
  useRef,
  useEffect,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react"
import { useChatDispatch, useTransport } from "./context"
import { arrowUpCircleFill } from "../utils/icons"

export interface ChatInputProps {
  inputId: string
  disabled: boolean
  placeholder: string
  value: string
}

export interface ChatInputHandle {
  setInputValue(
    value: string,
    options?: { submit?: boolean; focus?: boolean },
  ): void
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ inputId, disabled, placeholder, value }, ref) {
    const dispatch = useChatDispatch()
    const transport = useTransport()

    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const isComposingRef = useRef(false)

    // Update textarea value when the controlled `value` prop changes
    useEffect(() => {
      const el = textareaRef.current
      if (!el) return
      if (el.value !== value) {
        el.value = value
      }
      updateHeight(el)
    }, [value])

    function updateHeight(el: HTMLTextAreaElement): void {
      if (el.scrollHeight === 0) return
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }

    function isSendDisabled(): boolean {
      const el = textareaRef.current
      if (!el) return true
      return disabled || el.value.trim().length === 0
    }

    const sendInput = useCallback(
      (focusAfter = true): void => {
        const el = textareaRef.current
        if (!el) return
        const content = el.value
        if (content.trim().length === 0) return
        if (disabled) return

        dispatch({ type: "INPUT_SENT", content, role: "user" })
        transport.sendInput(inputId, content)

        // value is cleared via state (INPUT_SENT sets inputValue: ""),
        // but we also clear the DOM element immediately to avoid lag
        el.value = ""
        updateHeight(el)

        if (focusAfter) el.focus()
      },
      [disabled, dispatch, transport, inputId],
    )

    const onKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
        const isEnter = e.code === "Enter" && !e.shiftKey
        const el = textareaRef.current
        if (!el) return
        if (isEnter && !isComposingRef.current && el.value.trim().length > 0) {
          e.preventDefault()
          sendInput()
        }
      },
      [sendInput],
    )

    const onInput = useCallback((): void => {
      const el = textareaRef.current
      if (!el) return
      updateHeight(el)
      // Force button re-render by triggering a re-render via textarea input events.
      // Since the button disabled state is derived imperatively, we manage it via
      // the DOM directly here to avoid an extra useState.
      const btn = el.parentElement?.querySelector<HTMLButtonElement>(
        ".shiny-chat-btn-send",
      )
      if (btn) {
        btn.disabled = disabled ? true : el.value.trim().length === 0
      }
    }, [disabled])

    const onCompositionStart = useCallback((): void => {
      isComposingRef.current = true
    }, [])

    const onCompositionEnd = useCallback((): void => {
      isComposingRef.current = false
    }, [])

    // Expose imperative setInputValue for suggestions and programmatic control
    useImperativeHandle(
      ref,
      () => ({
        setInputValue(
          newValue: string,
          { submit = false, focus = false }: { submit?: boolean; focus?: boolean } = {},
        ): void {
          const el = textareaRef.current
          if (!el) return

          const oldValue = el.value
          el.value = newValue

          // Trigger auto-resize + button state update
          const inputEvent = new Event("input", { bubbles: true, cancelable: true })
          el.dispatchEvent(inputEvent)

          if (submit) {
            sendInput(false)
            if (oldValue) {
              el.value = oldValue
              const evt = new Event("input", { bubbles: true, cancelable: true })
              el.dispatchEvent(evt)
            }
          }

          if (focus) {
            el.focus()
          }
        },
      }),
      [sendInput],
    )

    const sendButtonDisabled = disabled || value.trim().length === 0

    return (
      <>
        <textarea
          ref={textareaRef}
          id={inputId}
          className="form-control"
          rows={1}
          placeholder={placeholder}
          defaultValue={value}
          onKeyDown={onKeyDown}
          onInput={onInput}
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          data-shiny-no-bind-input
        />
        <button
          type="button"
          className="shiny-chat-btn-send"
          title="Send message"
          aria-label="Send message"
          disabled={sendButtonDisabled}
          onClick={() => sendInput()}
          dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
        />
      </>
    )
  },
)
