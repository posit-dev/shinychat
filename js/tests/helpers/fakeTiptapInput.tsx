import { forwardRef, useImperativeHandle, useState } from "react"
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

    useImperativeHandle(
      ref,
      () => ({
        setInputValue(newValue, options = {}) {
          setValue(newValue)
          onHasTextChange(newValue.trim().length > 0)
          if (options.submit) {
            return onSubmit(newValue)
          }
          return true
        },
        focus() {},
        serializeEditor() {
          return value
        },
      }),
      [value, onHasTextChange, onSubmit],
    )

    return (
      <textarea
        aria-label="Chat message"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          setValue(e.target.value)
          onHasTextChange(e.target.value.trim().length > 0)
        }}
        onKeyDown={(e) => {
          const isModEnter = e.key === "Enter" && (e.metaKey || e.ctrlKey)
          const isPlainEnter = e.key === "Enter" && !e.metaKey && !e.ctrlKey
          const shouldSubmit =
            submitKey === "enter+modifier" ? isModEnter : isPlainEnter
          if (shouldSubmit) {
            e.preventDefault()
            const isBlank = value.trim().length === 0
            if (isBlank && !canSubmitEmpty?.()) return
            if (onSubmit(value)) {
              setValue("")
              onHasTextChange(false)
            }
          }
        }}
      />
    )
  },
)
