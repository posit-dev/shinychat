import {
  useState,
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
  onSend?: () => void
}

export interface ChatInputHandle {
  setInputValue(
    value: string,
    options?: { submit?: boolean; focus?: boolean },
  ): void
  focus(): void
}

export const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  function ChatInput({ inputId, disabled, placeholder, value, onSend }, ref) {
    const dispatch = useChatDispatch()
    const transport = useTransport()

    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const isComposingRef = useRef(false)
    const [hasText, setHasText] = useState(value.trim().length > 0)

    // Update textarea value when the controlled `value` prop changes
    useEffect(() => {
      const el = textareaRef.current
      if (!el) return
      if (el.value !== value) {
        el.value = value
      }
      setHasText(value.trim().length > 0)
      updateHeight(el)
    }, [value])

    function updateHeight(el: HTMLTextAreaElement): void {
      if (el.scrollHeight === 0) return
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
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
        onSend?.()

        // value is cleared via state (INPUT_SENT sets inputValue: ""),
        // but we also clear the DOM element immediately to avoid lag
        el.value = ""
        setHasText(false)
        updateHeight(el)

        if (focusAfter) el.focus()
      },
      [disabled, dispatch, transport, inputId, onSend],
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
      setHasText(el.value.trim().length > 0)
    }, [])

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
          {
            submit = false,
            focus = false,
          }: { submit?: boolean; focus?: boolean } = {},
        ): void {
          const el = textareaRef.current
          if (!el) return

          const oldValue = el.value
          el.value = newValue
          setHasText(newValue.trim().length > 0)
          updateHeight(el)

          if (submit) {
            // Directly send without going through sendInput — bypasses
            // the disabled check since the server explicitly asked to submit.
            const submitContent = el.value
            if (submitContent.trim().length > 0) {
              dispatch({
                type: "INPUT_SENT",
                content: submitContent,
                role: "user",
                preserveInputValue: true,
              })
              transport.sendInput(inputId, submitContent)
              onSend?.()
            }
            // Always restore old value (the submitted value was temporary)
            el.value = oldValue
            setHasText(oldValue.trim().length > 0)
            updateHeight(el)
          }

          if (focus) {
            el.focus()
          }
        },
        focus(): void {
          textareaRef.current?.focus()
        },
      }),
      [dispatch, transport, inputId, onSend],
    )

    const sendButtonDisabled = disabled || !hasText

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
