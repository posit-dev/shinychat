import {
  useState,
  useRef,
  useCallback,
  useEffect,
  useMemo,
  forwardRef,
  useImperativeHandle,
  memo,
} from "react"
import { useChatDispatch } from "./context"
import { useInputHistory } from "./useInputHistory"
import type {
  ChatTransport,
  SlashCommandDef,
  SlashCommandEventDetail,
} from "../transport/types"
import { arrowUpCircleFill, spinnerArc, stopCircleFill } from "../utils/icons"
import { SlashCommandPalette, filterSlashCommands } from "./SlashCommandPalette"

export interface ChatInputProps {
  transport: ChatTransport
  inputId: string
  disabled: boolean
  hasTopShadow?: boolean
  placeholder: string
  onSend?: () => void
  userMessages: string[]
  enableCancel?: boolean
  cancelRequested?: boolean
  isStreaming?: boolean
  onCancel?: () => void
  slashCommands?: SlashCommandDef[]
  slashCommandId?: string
}

export interface ChatInputHandle {
  setInputValue(
    value: string,
    options?: { submit?: boolean; focus?: boolean },
  ): void
  focus(): void
}

function parseSlashCommand(
  value: string,
  commands: SlashCommandDef[],
): { command: string; userText: string; echo: boolean } | null {
  if (!value.startsWith("/")) return null
  const withoutSlash = value.slice(1)
  const spaceIndex = withoutSlash.indexOf(" ")
  const commandName =
    spaceIndex === -1 ? withoutSlash : withoutSlash.slice(0, spaceIndex)
  const userText =
    spaceIndex === -1 ? "" : withoutSlash.slice(spaceIndex + 1).trim()
  const matched = commands.find((cmd) => cmd.name === commandName)
  if (!matched) return null
  return { command: commandName, userText, echo: matched.echo }
}

function getSlashFilter(value: string): string {
  if (!value.startsWith("/")) return ""
  const withoutSlash = value.slice(1)
  const spaceIndex = withoutSlash.indexOf(" ")
  return spaceIndex === -1 ? withoutSlash : ""
}

export const ChatInput = memo(
  forwardRef<ChatInputHandle, ChatInputProps>(function ChatInput(
    {
      transport,
      inputId,
      disabled,
      hasTopShadow = false,
      placeholder,
      onSend,
      userMessages,
      enableCancel,
      cancelRequested,
      isStreaming,
      onCancel,
      slashCommands = [],
      slashCommandId = "",
    },
    ref,
  ) {
    const dispatch = useChatDispatch()

    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const isComposingRef = useRef(false)
    const [hasText, setHasText] = useState(false)
    const [paletteOpen, setPaletteOpen] = useState(false)
    const [slashFilter, setSlashFilter] = useState("")
    const [highlightedIndex, setHighlightedIndex] = useState(0)
    const { recall, reset, isActive } = useInputHistory(userMessages)

    // Single source of truth for the palette's contents and selection. The
    // keyboard handler, the `aria-activedescendant`, and the palette itself all
    // read from these so they can't drift apart.
    const filteredCommands = useMemo(
      () =>
        paletteOpen ? filterSlashCommands(slashCommands, slashFilter) : [],
      [paletteOpen, slashCommands, slashFilter],
    )
    const effectiveIndex =
      filteredCommands.length === 0
        ? -1
        : Math.min(highlightedIndex, filteredCommands.length - 1)

    function updateHeight(el: HTMLTextAreaElement): void {
      if (el.scrollHeight === 0) return
      el.style.height = "auto"
      el.style.height = `${el.scrollHeight}px`
    }

    const selectCommand = useCallback((cmd: SlashCommandDef) => {
      const el = textareaRef.current
      if (!el) return
      el.value = `/${cmd.name} `
      setHasText(true)
      updateHeight(el)
      setPaletteOpen(false)
      setSlashFilter("")
      setHighlightedIndex(0)
      el.focus()
    }, [])

    const submitValue = useCallback(
      (content: string): boolean => {
        if (content.trim().length === 0) return false
        if (disabled) return false

        setPaletteOpen(false)

        const slashMatch = parseSlashCommand(content, slashCommands)
        if (slashMatch) {
          const containerEl =
            textareaRef.current?.closest<HTMLElement>("shiny-chat-container") ??
            null
          const detail: SlashCommandEventDetail = {
            id:
              containerEl?.getAttribute("effective-id") ??
              containerEl?.id ??
              "",
            command: slashMatch.command,
            userText: slashMatch.userText,
            echo: slashMatch.echo,
          }
          const ev = new CustomEvent("shiny:chat-slash-command", {
            detail,
            cancelable: true,
            bubbles: true,
          })
          ;(containerEl ?? textareaRef.current)?.dispatchEvent(ev)

          const echo = detail.echo
          const prevented = ev.defaultPrevented

          if (echo) {
            dispatch({
              type: "INPUT_SENT",
              content,
              role: "user",
              // await a response only when the server will handle it
              awaitResponse: !prevented,
            })
          }
          if (!prevented) {
            transport.sendSlashCommand(
              slashCommandId,
              slashMatch.command,
              slashMatch.userText,
              echo,
            )
          }
        } else {
          dispatch({ type: "INPUT_SENT", content, role: "user" })
          transport.sendInput(inputId, content)
        }
        onSend?.()
        reset()
        return true
      },
      [
        disabled,
        dispatch,
        transport,
        inputId,
        onSend,
        reset,
        slashCommands,
        slashCommandId,
      ],
    )

    const sendInput = useCallback(
      (focusAfter = true): void => {
        const el = textareaRef.current
        if (!el) return
        if (!submitValue(el.value)) return

        // Clear the DOM element directly (textarea is fully uncontrolled)
        el.value = ""
        setHasText(false)
        updateHeight(el)

        if (focusAfter) el.focus()
      },
      [submitValue],
    )

    const onKeyDown = useCallback(
      (e: React.KeyboardEvent<HTMLTextAreaElement>): void => {
        const isEnter = e.code === "Enter" && !e.shiftKey
        const el = textareaRef.current
        if (!el) return

        if (paletteOpen) {
          if (e.key === "ArrowDown") {
            e.preventDefault()
            setHighlightedIndex((prev) =>
              filteredCommands.length === 0
                ? 0
                : (prev + 1) % filteredCommands.length,
            )
            return
          }
          if (e.key === "ArrowUp") {
            e.preventDefault()
            setHighlightedIndex((prev) =>
              filteredCommands.length === 0
                ? 0
                : (prev - 1 + filteredCommands.length) %
                  filteredCommands.length,
            )
            return
          }
          if (e.key === "Enter" || e.key === "Tab") {
            e.preventDefault()
            const selected =
              effectiveIndex >= 0 ? filteredCommands[effectiveIndex] : undefined
            if (selected) {
              selectCommand(selected)
            }
            return
          }
          if (e.key === "Escape") {
            e.preventDefault()
            setPaletteOpen(false)
            setSlashFilter("")
            return
          }
        }

        const isUp = e.code === "ArrowUp"
        const isDown = e.code === "ArrowDown"

        const atEnd = el.selectionStart === el.value.length
        const canRecall = isActive() ? atEnd : el.value.length === 0

        if ((isUp || isDown) && canRecall && !isComposingRef.current) {
          const value = recall(isUp ? "up" : "down", el.value)
          if (value !== undefined) {
            e.preventDefault()
            el.value = value
            updateHeight(el)
            setHasText(value.trim().length > 0)
            el.setSelectionRange(value.length, value.length)
          }
          return
        }

        if (isEnter && !isComposingRef.current && el.value.trim().length > 0) {
          e.preventDefault()
          sendInput()
        }
      },
      [
        sendInput,
        recall,
        isActive,
        paletteOpen,
        filteredCommands,
        effectiveIndex,
        selectCommand,
      ],
    )

    const onInput = useCallback((): void => {
      const el = textareaRef.current
      if (!el) return
      const value = el.value

      if (
        value.startsWith("/") &&
        !value.includes(" ") &&
        slashCommands.length > 0
      ) {
        setPaletteOpen(true)
        setSlashFilter(getSlashFilter(value))
        setHighlightedIndex(0)
      } else {
        setPaletteOpen(false)
        setSlashFilter("")
      }

      setHasText(value.trim().length > 0)
      updateHeight(el)
    }, [slashCommands])

    // Slash commands arrive asynchronously from the server. If they show up
    // after the user has already typed a qualifying "/" prefix (the palette is
    // opened by input events, so a late arrival would otherwise go unnoticed),
    // open the palette as soon as they're available.
    useEffect(() => {
      const el = textareaRef.current
      if (!el) return
      const value = el.value
      if (
        value.startsWith("/") &&
        !value.includes(" ") &&
        slashCommands.length > 0
      ) {
        setPaletteOpen(true)
        setSlashFilter(getSlashFilter(value))
        setHighlightedIndex(0)
      }
    }, [slashCommands])

    const onCompositionStart = useCallback((): void => {
      isComposingRef.current = true
    }, [])

    const onCompositionEnd = useCallback((): void => {
      isComposingRef.current = false
    }, [])

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
            // Server-triggered submit still respects the disabled guard
            // (we only skip sendInput() to avoid its focus/clear side-effects).
            submitValue(el.value)
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
      [submitValue],
    )

    const sendButtonDisabled = disabled || !hasText
    const isPending = disabled && !isStreaming
    const showCancelButton = !!enableCancel && !!isStreaming && !cancelRequested
    const showSpinner = isPending || !!cancelRequested

    const paletteId = `${inputId}-slash-palette`
    const activeCommand =
      effectiveIndex >= 0 ? filteredCommands[effectiveIndex] : undefined
    const activeDescendant = activeCommand
      ? `${paletteId}-item-${activeCommand.name}`
      : undefined

    return (
      <>
        {paletteOpen && (
          <SlashCommandPalette
            id={paletteId}
            commands={filteredCommands}
            effectiveIndex={effectiveIndex}
            onSelect={selectCommand}
            onHighlight={setHighlightedIndex}
          />
        )}
        <textarea
          ref={textareaRef}
          id={inputId}
          className={hasTopShadow ? "form-control shadow" : "form-control"}
          rows={1}
          placeholder={placeholder}
          aria-disabled={disabled || undefined}
          onKeyDown={onKeyDown}
          onInput={onInput}
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          onBlur={() => setPaletteOpen(false)}
          aria-label="Chat message"
          aria-haspopup={slashCommands.length > 0 ? "listbox" : undefined}
          aria-expanded={paletteOpen || undefined}
          aria-controls={paletteOpen ? paletteId : undefined}
          aria-activedescendant={activeDescendant}
          data-shiny-no-bind-input
        />
        {showCancelButton ? (
          <button
            type="button"
            className="shiny-chat-btn-send shiny-chat-btn-cancel"
            title="Stop generating"
            aria-label="Stop generating"
            onClick={onCancel}
            dangerouslySetInnerHTML={{ __html: stopCircleFill }}
          />
        ) : showSpinner ? (
          <button
            type="button"
            className={`shiny-chat-btn-send shiny-chat-btn-spinner${cancelRequested ? " shiny-chat-btn-cancel" : ""}`}
            aria-label="Loading"
            dangerouslySetInnerHTML={{ __html: spinnerArc }}
          />
        ) : (
          <button
            type="button"
            className="shiny-chat-btn-send"
            title="Send message"
            aria-label="Send message"
            disabled={sendButtonDisabled}
            onClick={() => sendInput()}
            dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
          />
        )}
      </>
    )
  }),
)
