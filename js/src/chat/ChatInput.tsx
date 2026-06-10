import {
  useState,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
  memo,
} from "react"
import { useChatDispatch } from "./context"
import type {
  ChatTransport,
  SlashCommandDef,
  SlashCommandEventDetail,
} from "../transport/types"
import { arrowUpCircleFill, spinnerArc, stopCircleFill } from "../utils/icons"
import { TiptapInput, type TiptapInputHandle } from "./TiptapInput"

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
    const tiptapRef = useRef<TiptapInputHandle>(null)
    const [hasText, setHasText] = useState(false)

    const submitValue = useCallback(
      (content: string): boolean => {
        if (content.trim().length === 0) return false
        if (disabled) return false

        const slashMatch = parseSlashCommand(content, slashCommands)
        if (slashMatch) {
          const inputEl = document.getElementById(inputId)
          const containerEl =
            inputEl?.closest<HTMLElement>("shiny-chat-container") ?? null
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
          ;(containerEl ?? inputEl)?.dispatchEvent(ev)

          const echo = detail.echo
          const prevented = ev.defaultPrevented

          if (echo) {
            dispatch({
              type: "INPUT_SENT",
              content,
              role: "user",
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
        return true
      },
      [
        disabled,
        dispatch,
        transport,
        inputId,
        onSend,
        slashCommands,
        slashCommandId,
      ],
    )

    useImperativeHandle(
      ref,
      () => ({
        setInputValue(value, options) {
          tiptapRef.current?.setInputValue(value, options)
        },
        focus() {
          tiptapRef.current?.focus()
        },
      }),
      [],
    )

    const sendButtonDisabled = disabled || !hasText
    const isPending = disabled && !isStreaming
    const showCancelButton = !!enableCancel && !!isStreaming && !cancelRequested
    const showSpinner = isPending || !!cancelRequested

    return (
      <>
        <TiptapInput
          ref={tiptapRef}
          inputId={inputId}
          disabled={disabled}
          placeholder={placeholder}
          hasTopShadow={hasTopShadow}
          slashCommands={slashCommands}
          onHasTextChange={setHasText}
          onSubmit={submitValue}
          userMessages={userMessages}
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
            onClick={() => {
              const content = tiptapRef.current?.serializeEditor() ?? ""
              if (submitValue(content)) {
                tiptapRef.current?.setInputValue("")
              }
            }}
            dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
          />
        )}
      </>
    )
  }),
)
