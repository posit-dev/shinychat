import {
  useState,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
  memo,
} from "react"
import { useChatDispatch, useChatSubmit } from "./context"
import type {
  ChatTransport,
  SlashCommandDef,
  SlashCommandEventDetail,
} from "../transport/types"
import { arrowUpCircleFill, spinnerArc, stopCircleFill } from "../utils/icons"
import { TiptapInput, type TiptapInputHandle } from "./TiptapInput"
import type { SubmitKey } from "./tiptap/submitShortcut"
import { type AttachmentPayload } from "./attachments"
import { useAttachmentStaging } from "./useAttachmentStaging"
import { AttachmentTray } from "./AttachmentTray"

export interface ChatInputProps {
  transport: ChatTransport
  inputId: string
  uploadAccept: string[]
  maxUploadSize: number | null
  disabled: boolean
  hasTopShadow?: boolean
  placeholder: string
  onSend?: () => void
  userMessages: string[]
  enableCancel?: boolean
  enableUpload?: boolean
  cancelRequested?: boolean
  isStreaming?: boolean
  onCancel?: () => void
  slashCommands?: SlashCommandDef[]
  slashCommandId?: string
  submitKey?: SubmitKey
  iconSend?: string
}

export interface ChatInputHandle {
  setInputValue(
    value: string | undefined,
    options?: {
      submit?: boolean
      focus?: boolean
      attachments?: AttachmentPayload[]
      attachmentMode?: "append" | "set"
    },
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
      uploadAccept,
      maxUploadSize,
      disabled,
      hasTopShadow = false,
      placeholder,
      onSend,
      userMessages,
      enableCancel,
      enableUpload,
      cancelRequested,
      isStreaming,
      onCancel,
      slashCommands = [],
      slashCommandId = "",
      submitKey = "enter",
      iconSend,
    },
    ref,
  ) {
    const dispatch = useChatDispatch()
    const submitUserInput = useChatSubmit()
    const tiptapRef = useRef<TiptapInputHandle>(null)
    const [hasText, setHasText] = useState(false)
    const focusEditor = useCallback(() => tiptapRef.current?.focus(), [])
    const staging = useAttachmentStaging({
      uploadAccept,
      maxUploadSize,
      enableUpload,
      focusEditor,
    })
    const {
      attachments,
      onPaste,
      onDrop,
      getPayloads,
      applyPayloads,
      clearAttachments,
      resetAll,
    } = staging

    const submitValue = useCallback(
      (content: string): boolean => {
        const payloads = getPayloads()
        if (content.trim().length === 0 && payloads.length === 0) return false
        if (disabled) return false

        const slashMatch = parseSlashCommand(content, slashCommands)
        if (slashMatch) {
          // Slash commands don't carry files; staged attachments stay in the
          // tray so they can be sent with a regular message afterwards.
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
          submitUserInput(content, payloads)
          resetAll()
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
        submitUserInput,
        getPayloads,
        resetAll,
      ],
    )

    // Lets Enter submit an attachments-only message even though the editor
    // doc is empty (TiptapInput blocks empty submits otherwise).
    const canSubmitEmpty = useCallback(
      () => getPayloads().length > 0,
      [getPayloads],
    )

    useImperativeHandle(
      ref,
      () => ({
        setInputValue(
          newValue: string | undefined,
          {
            submit = false,
            focus = false,
            attachments,
            attachmentMode = "append",
          }: {
            submit?: boolean
            focus?: boolean
            attachments?: AttachmentPayload[]
            attachmentMode?: "append" | "set"
          } = {},
        ): void {
          const tiptap = tiptapRef.current
          if (!tiptap) return

          if (!submit) {
            if (newValue !== undefined) {
              tiptap.setInputValue(newValue, { focus })
            } else if (focus) {
              tiptap.focus()
            }
            if (attachments !== undefined) {
              applyPayloads(attachments, attachmentMode)
            }
            return
          }

          // Submit: stage the provided value (if any), send, then restore the
          // user's draft — the submitted value never clobbers what was typed.
          const oldValue = tiptap.serializeEditor()
          if (newValue !== undefined) {
            tiptap.setInputValue(newValue)
          }
          const submitContent = tiptap.serializeEditor()
          const newPayloads = attachments ?? []
          const submitAttachments =
            attachmentMode === "append"
              ? [...getPayloads(), ...newPayloads]
              : newPayloads

          if (submitAttachments.length === 0) {
            // No attachments in play — reuse the interactive path so slash
            // commands submitted programmatically still execute.
            submitValue(submitContent)
          } else if (!disabled && submitAttachments.length > 0) {
            submitUserInput(submitContent, submitAttachments)
            onSend?.()
          }

          if (newValue !== undefined) {
            tiptap.setInputValue(oldValue, { focus })
          } else if (focus) {
            tiptap.focus()
          }
          if (attachments !== undefined) {
            clearAttachments()
          }
        },
        focus(): void {
          tiptapRef.current?.focus()
        },
      }),
      [
        disabled,
        onSend,
        submitValue,
        submitUserInput,
        applyPayloads,
        getPayloads,
        clearAttachments,
      ],
    )

    type SendButtonState =
      | "empty"
      | "ready"
      | "pending"
      | "cancel"
      | "cancelling"

    const hasContent = hasText || attachments.length > 0
    const sendButtonState: SendButtonState = cancelRequested
      ? "cancelling"
      : !!enableCancel && !!isStreaming
        ? "cancel"
        : disabled
          ? "pending" // also covers isStreaming && !enableCancel, a pre-existing ambiguous case
          : hasContent
            ? "ready"
            : "empty"

    const sendButtonIcon =
      sendButtonState === "cancel"
        ? stopCircleFill
        : sendButtonState === "pending" || sendButtonState === "cancelling"
          ? spinnerArc
          : (iconSend ?? arrowUpCircleFill)

    const sendButtonLabel =
      sendButtonState === "cancel"
        ? "Stop generating"
        : sendButtonState === "pending" || sendButtonState === "cancelling"
          ? "Loading"
          : "Send message"

    // Only "empty" gets the native disabled attribute (matches prior
    // behavior); "pending"/"cancelling" are non-interactive via CSS
    // (pointer-events: none) only, so they don't trigger the :disabled
    // color rule and keep their state-driven color instead of turning gray.
    const sendButtonDisabled = sendButtonState === "empty"

    const handleSendClick =
      sendButtonState === "cancel"
        ? onCancel
        : sendButtonState === "ready"
          ? () => {
              const content = tiptapRef.current?.serializeEditor() ?? ""
              if (submitValue(content)) {
                tiptapRef.current?.setInputValue("")
                tiptapRef.current?.focus()
              }
            }
          : undefined

    return (
      // The whole input region is a drop zone, so files can be dropped onto
      // the attachment tray (not just the editor) when attachments exist.
      <div
        className="shiny-chat-input-dropzone"
        onDropCapture={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onPasteCapture={onPaste}
      >
        <AttachmentTray
          staging={staging}
          uploadAccept={uploadAccept}
          maxUploadSize={maxUploadSize}
          enableUpload={enableUpload}
          disabled={disabled}
        />
        <TiptapInput
          ref={tiptapRef}
          inputId={inputId}
          placeholder={placeholder}
          hasTopShadow={hasTopShadow}
          slashCommands={slashCommands}
          onHasTextChange={setHasText}
          onSubmit={submitValue}
          userMessages={userMessages}
          submitKey={submitKey}
          canSubmitEmpty={canSubmitEmpty}
        />
        <button
          type="button"
          className="shiny-chat-btn-send"
          data-state={sendButtonState}
          title={sendButtonLabel}
          aria-label={sendButtonLabel}
          disabled={sendButtonDisabled}
          onClick={handleSendClick}
          dangerouslySetInnerHTML={{ __html: sendButtonIcon }}
        />
      </div>
    )
  }),
)
