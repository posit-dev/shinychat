import {
  useState,
  useRef,
  useCallback,
  useLayoutEffect,
  useEffect,
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
import {
  arrowUpCircleFill,
  spinnerArc,
  stopCircleFill,
  plusThin,
} from "../utils/icons"
import { TiptapInput, type TiptapInputHandle } from "./TiptapInput"
import type { SubmitKey } from "./tiptap/submitShortcut"
import {
  processFile,
  totalBytes,
  formatBytes,
  acceptAttribute,
  attachmentBadgeLabel,
  pastedTextFile,
  PASTE_AS_FILE_MIN_CHARS,
  attachmentFamily,
  type AttachedFile,
  type AttachmentPayload,
} from "./attachments"
import { uuid } from "../utils/uuid"
import { TextAttachmentPreview } from "./TextAttachmentPreview"

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

function toPayload(a: AttachedFile): AttachmentPayload {
  return { mime: a.type, data_url: a.dataUrl, name: a.name, size: a.size }
}

function toAttachedFiles(payloads: AttachmentPayload[]): AttachedFile[] {
  return payloads.map((a) => ({
    id: uuid(),
    type: a.mime,
    family: attachmentFamily(a.mime) ?? ("document" as const),
    dataUrl: a.data_url,
    name: a.name,
    size: a.size,
  }))
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
    },
    ref,
  ) {
    const dispatch = useChatDispatch()
    const tiptapRef = useRef<TiptapInputHandle>(null)
    const [hasText, setHasText] = useState(false)
    const [attachments, setAttachments] = useState<AttachedFile[]>([])
    const stagedRef = useRef<AttachedFile[]>([])

    useEffect(() => {
      stagedRef.current = attachments
    }, [attachments])

    const [downscaleNotice, setDownscaleNotice] = useState(false)
    const [gifConvertedNotice, setGifConvertedNotice] = useState(false)
    const [sizeNotice, setSizeNotice] = useState(false)
    const fileInputRef = useRef<HTMLInputElement>(null)

    const addFiles = useCallback(
      async (files: FileList | File[]): Promise<void> => {
        const processed: {
          file: AttachedFile
          wasDownscaled: boolean
          wasConverted: boolean
        }[] = []
        for (const file of Array.from(files)) {
          let result: Awaited<ReturnType<typeof processFile>> = null
          try {
            result = await processFile(file, uploadAccept)
          } catch {
            continue
          }
          if (result) processed.push(result)
        }
        if (processed.length === 0) {
          tiptapRef.current?.focus()
          return
        }

        let overSize = false
        let downscaled = false
        let converted = false
        setAttachments((prev) => {
          let bytes = totalBytes(prev)
          const fits: AttachedFile[] = []
          for (const { file, wasDownscaled, wasConverted } of processed) {
            if (maxUploadSize !== null && bytes + file.size > maxUploadSize) {
              overSize = true
              continue
            }
            fits.push(file)
            bytes += file.size
            if (wasDownscaled) downscaled = true
            if (wasConverted) converted = true
          }
          return fits.length > 0 ? [...prev, ...fits] : prev
        })
        if (overSize) setSizeNotice(true)
        if (downscaled) setDownscaleNotice(true)
        if (converted) setGifConvertedNotice(true)
        tiptapRef.current?.focus()
      },
      [uploadAccept, maxUploadSize],
    )

    const removeAttachment = useCallback((id: string): void => {
      // Removing only lowers the running total, so any prior size-cap notice
      // is now stale — clear it on every removal.
      setSizeNotice(false)
      setAttachments((prev) => {
        const next = prev.filter((a) => a.id !== id)
        if (next.length === 0) {
          setDownscaleNotice(false)
          setGifConvertedNotice(false)
        }
        return next
      })
    }, [])

    // DOM nodes of the staged-attachment containers, indexed by position, so a
    // keyboard removal can shift focus to the right sibling afterwards.
    const attachmentRefs = useRef<(HTMLDivElement | null)[]>([])
    // The slot to focus once the post-removal render commits: a numeric index
    // into the shrunken list, or "input" when nothing remains.
    const pendingFocusRef = useRef<number | "input" | null>(null)

    const removeAttachmentByKeyboard = useCallback(
      (index: number): void => {
        const nextLen = attachments.length - 1
        // Prefer the next attachment (which slides into `index`); fall back to
        // the new last one when the removed item was itself last.
        pendingFocusRef.current =
          nextLen === 0 ? "input" : Math.min(index, nextLen - 1)
        removeAttachment(attachments[index]!.id)
      },
      [attachments, removeAttachment],
    )

    useLayoutEffect(() => {
      const target = pendingFocusRef.current
      if (target === null) return
      pendingFocusRef.current = null
      if (target === "input") {
        tiptapRef.current?.focus()
      } else {
        attachmentRefs.current[target]?.focus()
      }
    }, [attachments])

    // Capture-phase so file and long-text pastes are intercepted before
    // Tiptap's own ProseMirror paste handler sees the event; a plain text
    // paste falls through to the editor untouched.
    const onPaste = useCallback(
      (e: React.ClipboardEvent<HTMLDivElement>): void => {
        if (!enableUpload) return
        const data = e.clipboardData
        if (!data) return
        const files: File[] = []
        for (const item of Array.from(data.items)) {
          if (item.kind === "file" && uploadAccept.includes(item.type)) {
            const f = item.getAsFile()
            if (f) files.push(f)
          }
        }
        if (files.length > 0) {
          e.preventDefault()
          e.stopPropagation()
          void addFiles(files)
          return
        }
        // Only intercept when the conversion will succeed (text uploads accepted),
        // so a large paste is never silently dropped.
        const text = data.getData("text/plain")
        if (
          text.length > PASTE_AS_FILE_MIN_CHARS &&
          uploadAccept.includes("text/plain")
        ) {
          e.preventDefault()
          e.stopPropagation()
          void addFiles([pastedTextFile(text)])
        }
      },
      [addFiles, enableUpload, uploadAccept],
    )

    // Capture-phase for the same reason as paste: ProseMirror would otherwise
    // handle the drop itself and insert the dropped content into the doc.
    const onDrop = useCallback(
      (e: React.DragEvent<HTMLDivElement>): void => {
        if (!enableUpload) return
        if (!e.dataTransfer?.files?.length) return
        e.preventDefault()
        e.stopPropagation()
        void addFiles(e.dataTransfer.files)
      },
      [addFiles, enableUpload],
    )

    const onFilePick = useCallback(
      (e: React.ChangeEvent<HTMLInputElement>): void => {
        if (e.target.files) void addFiles(e.target.files)
        e.target.value = ""
      },
      [addFiles],
    )

    const submitValue = useCallback(
      (content: string): boolean => {
        const payloads = stagedRef.current.map(toPayload)
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
          dispatch({
            type: "INPUT_SENT",
            content,
            role: "user",
            ...(payloads.length > 0 ? { attachments: payloads } : {}),
          })
          // The wire shape signals the upload mode: a bare string when
          // enableUpload is off (back-compat with the historical string input),
          // or {text, attachments} when it is on.
          transport.sendInput(
            inputId,
            enableUpload ? { text: content, attachments: payloads } : content,
          )
          setAttachments([])
          setDownscaleNotice(false)
          setGifConvertedNotice(false)
          setSizeNotice(false)
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
        enableUpload,
      ],
    )

    // Lets Enter submit an attachments-only message even though the editor
    // doc is empty (TiptapInput blocks empty submits otherwise).
    const canSubmitEmpty = useCallback(() => stagedRef.current.length > 0, [])

    // Clicking the empty space of the attachments tray focuses the editor
    // (clicks on a thumbnail or its remove button pass through untouched).
    const onAttachmentsMouseDown = useCallback(
      (e: React.MouseEvent<HTMLDivElement>): void => {
        if (e.target === e.currentTarget) {
          e.preventDefault()
          tiptapRef.current?.focus()
        }
      },
      [],
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
              const newFiles = toAttachedFiles(attachments)
              if (attachmentMode === "append") {
                setAttachments((prev) => [...prev, ...newFiles])
              } else {
                setAttachments(newFiles)
              }
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
              ? [...stagedRef.current.map(toPayload), ...newPayloads]
              : newPayloads

          if (submitAttachments.length === 0) {
            // No attachments in play — reuse the interactive path so slash
            // commands submitted programmatically still execute.
            submitValue(submitContent)
          } else if (!disabled && submitAttachments.length > 0) {
            dispatch({
              type: "INPUT_SENT",
              content: submitContent,
              role: "user",
              attachments: submitAttachments,
            })
            transport.sendInput(
              inputId,
              enableUpload
                ? { text: submitContent, attachments: submitAttachments }
                : submitContent,
            )
            onSend?.()
          }

          if (newValue !== undefined) {
            tiptap.setInputValue(oldValue, { focus })
          } else if (focus) {
            tiptap.focus()
          }
          if (attachments !== undefined) {
            setAttachments([])
          }
        },
        focus(): void {
          tiptapRef.current?.focus()
        },
      }),
      [
        disabled,
        dispatch,
        transport,
        inputId,
        enableUpload,
        onSend,
        submitValue,
      ],
    )

    const sendButtonDisabled =
      disabled || (!hasText && attachments.length === 0)
    const isPending = disabled && !isStreaming
    const showCancelButton = !!enableCancel && !!isStreaming && !cancelRequested
    const showSpinner = isPending || !!cancelRequested

    return (
      // The whole input region is a drop zone, so files can be dropped onto
      // the attachment tray (not just the editor) when attachments exist.
      <div
        className="shiny-chat-input-dropzone"
        onDropCapture={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onPasteCapture={onPaste}
      >
        {attachments.length > 0 && (
          <div
            className="shiny-chat-input-attachments"
            onMouseDown={onAttachmentsMouseDown}
          >
            {attachments.map((a, i) => (
              <AttachmentPreview
                key={a.id}
                attachment={a}
                index={i}
                onRemove={() => removeAttachment(a.id)}
                onKeyboardRemove={() => removeAttachmentByKeyboard(i)}
                registerRef={(el) => {
                  attachmentRefs.current[i] = el
                }}
              />
            ))}
          </div>
        )}
        {(downscaleNotice || sizeNotice || gifConvertedNotice) && (
          <div className="shiny-chat-input-notice" role="status">
            {sizeNotice && maxUploadSize !== null && (
              <div>
                Attachments exceed the {formatBytes(maxUploadSize)} limit.
              </div>
            )}
            {downscaleNotice && (
              <div>Large image(s) were downscaled to fit.</div>
            )}
            {gifConvertedNotice && (
              <div>Animated GIF(s) were converted to a still image.</div>
            )}
          </div>
        )}
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
        {enableUpload && (
          <>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={acceptAttribute(uploadAccept)}
              style={{ display: "none" }}
              onChange={onFilePick}
              data-shiny-no-bind-input
            />
            <button
              type="button"
              className="shiny-chat-btn-attach"
              title="Attach file"
              aria-label="Attach file"
              disabled={disabled}
              onClick={() => fileInputRef.current?.click()}
              dangerouslySetInnerHTML={{ __html: plusThin }}
            />
          </>
        )}
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
                tiptapRef.current?.focus()
              }
            }}
            dangerouslySetInnerHTML={{ __html: arrowUpCircleFill }}
          />
        )}
      </div>
    )
  }),
)

const AttachmentPreview = memo(function AttachmentPreview({
  attachment,
  index,
  onRemove,
  onKeyboardRemove,
  registerRef,
}: {
  attachment: AttachedFile
  index: number
  onRemove: () => void
  onKeyboardRemove: () => void
  registerRef: (el: HTMLDivElement | null) => void
}) {
  // Shared focus/keyboard behavior applied to whichever root each variant
  // renders: a single tab stop per attachment, click-to-focus, and
  // Delete/Backspace to remove while focused.
  const containerProps: React.HTMLAttributes<HTMLDivElement> = {
    tabIndex: 0,
    "aria-label": attachment.name
      ? `Attachment: ${attachment.name}. Press Delete to remove.`
      : "Attachment. Press Delete to remove.",
    onClick: (e) => (e.currentTarget as HTMLDivElement).focus(),
    onKeyDown: (e) => {
      if (e.code === "Delete" || e.code === "Backspace") {
        e.preventDefault()
        onKeyboardRemove()
      }
    },
  }

  if (attachment.family === "image") {
    return (
      <div
        ref={registerRef}
        className="shiny-chat-input-thumbnail"
        title={attachment.name || undefined}
        {...containerProps}
      >
        <img
          src={attachment.dataUrl}
          alt={
            attachment.name
              ? `Attached image: ${attachment.name}`
              : `Attached image ${index + 1}`
          }
        />
        <button
          type="button"
          tabIndex={0}
          aria-label={
            attachment.name ? `Remove ${attachment.name}` : "Remove image"
          }
          onClick={onRemove}
        >
          ×
        </button>
      </div>
    )
  }
  if (attachment.family === "text") {
    return (
      <TextAttachmentPreview
        dataUrl={attachment.dataUrl}
        name={attachment.name}
        size={attachment.size}
        onRemove={onRemove}
        rootRef={registerRef}
        rootProps={containerProps}
      />
    )
  }
  return (
    <div
      ref={registerRef}
      className="shiny-chat-input-attachment-chip"
      title={attachment.name || undefined}
      {...containerProps}
    >
      <span className="shiny-chat-attachment-badge">
        {attachmentBadgeLabel(attachment.name, attachment.type)}
      </span>
      <span className="shiny-chat-attachment-meta">
        <span className="shiny-chat-attachment-name">
          {attachment.name || "attachment"}
        </span>
        <span className="shiny-chat-attachment-size">
          {formatBytes(attachment.size)}
        </span>
      </span>
      <button
        type="button"
        tabIndex={0}
        aria-label={
          attachment.name ? `Remove ${attachment.name}` : "Remove attachment"
        }
        onClick={onRemove}
      >
        ×
      </button>
    </div>
  )
})
