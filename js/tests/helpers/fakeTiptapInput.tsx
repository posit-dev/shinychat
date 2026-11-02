import { forwardRef, useImperativeHandle, useRef, useState } from "react"
import type {
  TiptapInputHandle,
  TiptapInputProps,
} from "../../src/chat/TiptapInput"

// Stand-in for TiptapInput used by tests that embed it (e.g. ChatMessage's
// edit box). jsdom's contenteditable div doesn't support fireEvent.change,
// so real typing can't be simulated against the genuine ProseMirror editor
// (see the skipped test in ChatApp.integration.test.tsx). A plain <textarea>
// gives the same public contract -- ref API plus onSubmit/onHasTextChange/
// submitKey -- with full fireEvent.change support. It mirrors TiptapInput's
// blank-submit gating (isBlank && !canSubmitEmpty?.() blocks submit) so
// consumers wiring up canSubmitEmpty get real coverage; slash-command
// behavior still isn't replicated and remains covered by ChatInput's tests.
export const FakeTiptapInput = forwardRef<TiptapInputHandle, TiptapInputProps>(
  function FakeTiptapInput(
    { placeholder, onHasTextChange, onSubmit, submitKey, canSubmitEmpty },
    ref,
  ) {
    const [value, setValue] = useState("")
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    // Ref mirror of the state value: serializeEditor must observe a
    // setInputValue() within the same synchronous call (as ProseMirror's doc
    // does), which React state alone cannot.
    const valueRef = useRef("")
    const setBoth = (next: string) => {
      valueRef.current = next
      setValue(next)
    }

    useImperativeHandle(
      ref,
      () => ({
        setInputValue(newValue, options = {}) {
          setBoth(newValue)
          onHasTextChange(newValue.trim().length > 0)
          if (options.submit) {
            return onSubmit(newValue)
          }
          if (options.focus) textareaRef.current?.focus()
          return true
        },
        // Unlike ProseMirror's focus (a jsdom no-op), a textarea can really
        // take focus, so tests can observe focus transfers via activeElement.
        focus() {
          textareaRef.current?.focus()
        },
        serializeEditor() {
          return valueRef.current
        },
      }),
      [onHasTextChange, onSubmit],
    )

    return (
      <textarea
        ref={textareaRef}
        aria-label="Chat message"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          setBoth(e.target.value)
          onHasTextChange(e.target.value.trim().length > 0)
        }}
        onKeyDown={(e) => {
          const isModEnter = e.key === "Enter" && (e.metaKey || e.ctrlKey)
          const isPlainEnter = e.key === "Enter" && !e.metaKey && !e.ctrlKey
          const shouldSubmit =
            submitKey === "enter+modifier" ? isModEnter : isPlainEnter
          if (shouldSubmit) {
            e.preventDefault()
            const isBlank = valueRef.current.trim().length === 0
            if (isBlank && !canSubmitEmpty?.()) return
            if (onSubmit(valueRef.current)) {
              setBoth("")
              onHasTextChange(false)
            }
          }
        }}
      />
    )
  },
)
