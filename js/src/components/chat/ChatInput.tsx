import { useEffect, useRef, useState, useCallback } from "preact/hooks"
import { JSX } from "preact/jsx-runtime"
import type { ChatInputSetInputOptions } from "./types"

export interface ChatInputProps {
  id?: string
  placeholder?: string
  disabled?: boolean
  value?: string
  onInputSent?: (value: string) => void
  onValueChange?: (value: string) => void
  autoFocus?: boolean
  // Accept a ref callback for external ref access
  inputRef?: (element: HTMLTextAreaElement | null) => void
}

export function ChatInput({
  id,
  placeholder = "Enter a message...",
  disabled = false,
  value: controlledValue,
  onInputSent,
  onValueChange,
  autoFocus = false,
  inputRef,
}: ChatInputProps): JSX.Element {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [internalValue, setInternalValue] = useState("")

  // Use controlled value if provided, otherwise use internal state
  const value = controlledValue !== undefined ? controlledValue : internalValue
  const setValue =
    controlledValue !== undefined ? onValueChange : setInternalValue

  const valueIsEmpty = value.trim().length === 0

  // Handle external ref callback
  useEffect(() => {
    if (inputRef && textareaRef.current) {
      inputRef(textareaRef.current)
    }
  }, [inputRef])

  // Auto-resize textarea
  const updateHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el || el.scrollHeight === 0) return

    el.style.height = "auto"
    el.style.height = `${el.scrollHeight}px`
  }, [])

  // Handle input changes
  const handleInput = useCallback(
    (e: Event) => {
      const target = e.target as HTMLTextAreaElement
      const newValue = target.value
      setValue?.(newValue)
      updateHeight()
    },
    [setValue, updateHeight],
  )

  // Handle key down events
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const isEnter = e.code === "Enter" && !e.shiftKey
      if (isEnter && !valueIsEmpty && !disabled) {
        e.preventDefault()
        sendInput()
      }
    },
    [valueIsEmpty, disabled],
  )

  // Send input
  const sendInput = useCallback(
    (focus = true) => {
      if (valueIsEmpty || disabled) return

      onInputSent?.(value)
      setValue?.("")

      if (focus) {
        textareaRef.current?.focus()
      }
    },
    [valueIsEmpty, disabled, value, onInputSent, setValue],
  )

  // Public method to set input value with options
  const setInputValue = useCallback(
    (
      newValue: string,
      { submit = false, focus = false }: ChatInputSetInputOptions = {},
    ) => {
      // Store previous value to restore post-submit (if submitting)
      const oldValue = value

      setValue?.(newValue)

      // Update height after setting value
      setTimeout(updateHeight, 0)

      if (submit) {
        setTimeout(() => {
          sendInput(false)
          if (oldValue) {
            setValue?.(oldValue)
            setTimeout(updateHeight, 0)
          }
        }, 0)
      }

      if (focus) {
        setTimeout(() => textareaRef.current?.focus(), 0)
      }
    },
    [value, setValue, updateHeight, sendInput],
  )

  // Expose setInputValue method via ref
  useEffect(() => {
    if (textareaRef.current) {
      ;(textareaRef.current as any).setInputValue = setInputValue
    }
  }, [setInputValue])

  // Update height when value changes
  useEffect(() => {
    updateHeight()
  }, [value, updateHeight])

  // Auto focus if requested
  useEffect(() => {
    if (autoFocus) {
      textareaRef.current?.focus()
    }
  }, [autoFocus])

  // Setup intersection observer for visibility
  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) updateHeight()
      })
    })

    observer.observe(textarea)

    return () => observer.disconnect()
  }, [updateHeight])

  const sendIcon = (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      fill="currentColor"
      viewBox="0 0 16 16"
    >
      <path d="M16 8A8 8 0 1 0 0 8a8 8 0 0 0 16 0m-7.5 3.5a.5.5 0 0 1-1 0V5.707L5.354 7.854a.5.5 0 1 1-.708-.708l3-3a.5.5 0 0 1 .708 0l3 3a.5.5 0 0 1-.708.708L8.5 5.707z" />
    </svg>
  )

  return (
    <div className="chat-input">
      <textarea
        ref={textareaRef}
        id={id}
        className="form-control"
        rows={1}
        placeholder={placeholder}
        value={value}
        disabled={disabled}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        data-shiny-no-bind-input
      />
      <button
        type="button"
        title="Send message"
        aria-label="Send message"
        disabled={disabled || valueIsEmpty}
        onClick={() => sendInput()}
      >
        {sendIcon}
      </button>
    </div>
  )
}
