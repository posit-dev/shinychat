import { useState, useRef, useCallback, useLayoutEffect } from "react"
import {
  processFile,
  totalBytes,
  attachmentFamily,
  pastedTextFile,
  PASTE_AS_FILE_MIN_CHARS,
  type AttachedFile,
  type AttachmentPayload,
} from "./attachments"
import { uuid } from "../utils/uuid"

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

export interface AttachmentStaging {
  attachments: AttachedFile[]
  /** True while an attachment is being processed. */
  processing: boolean
  /** Also guards the interval before the completed result commits. */
  isProcessing: () => boolean
  downscaleNotice: boolean
  gifConvertedNotice: boolean
  sizeNotice: boolean
  fileInputRef: React.RefObject<HTMLInputElement | null>
  attachmentRefs: React.MutableRefObject<(HTMLDivElement | null)[]>
  addFiles: (files: FileList | File[]) => Promise<void>
  removeAttachment: (id: string) => void
  removeAttachmentByKeyboard: (index: number) => void
  onPaste: (e: React.ClipboardEvent<HTMLDivElement>) => void
  onDrop: (e: React.DragEvent<HTMLDivElement>) => void
  onFilePick: (e: React.ChangeEvent<HTMLInputElement>) => void
  onAttachmentsMouseDown: (e: React.MouseEvent<HTMLDivElement>) => void
  /** Read the currently staged attachments in wire shape (for submit). */
  getPayloads: () => AttachmentPayload[]
  /**
   * Apply an externally-provided attachment list. Stable across renders (no
   * closure over `attachments`) so callers can depend on it in a `useEffect`
   * deps array without the effect re-firing on every add/remove.
   */
  applyPayloads: (payloads: AttachmentPayload[], mode: "append" | "set") => void
  /** Clear staged attachments only (leaves notices as-is). */
  clearAttachments: () => void
  /** Clear staged attachments and all notices. */
  resetAll: () => void
}

export function useAttachmentStaging({
  uploadAccept,
  maxUploadSize,
  enableUpload,
  focusEditor,
  canMutate,
}: {
  uploadAccept: string[]
  maxUploadSize: number | null
  enableUpload?: boolean
  focusEditor: () => void
  canMutate?: () => boolean
}): AttachmentStaging {
  const [stage, setStage] = useState<{
    attachments: AttachedFile[]
    downscaleNotice: boolean
    gifConvertedNotice: boolean
    sizeNotice: boolean
  }>({
    attachments: [],
    downscaleNotice: false,
    gifConvertedNotice: false,
    sizeNotice: false,
  })
  const { attachments, downscaleNotice, gifConvertedNotice, sizeNotice } = stage
  const stagedRef = useRef<AttachedFile[]>([])
  const processingRef = useRef({ count: 0, revision: 0, committedRevision: 0 })
  const [processingState, setProcessingState] = useState({
    count: 0,
    revision: 0,
  })
  const isProcessing = useCallback(() => {
    const current = processingRef.current
    return current.count > 0 || current.revision !== current.committedRevision
  }, [])

  useLayoutEffect(() => {
    // Publish the committed files before releasing the live submit guard.
    stagedRef.current = attachments
    processingRef.current.committedRevision = processingState.revision
  }, [attachments, processingState.revision])

  const fileInputRef = useRef<HTMLInputElement>(null)

  const addFiles = useCallback(
    async (files: FileList | File[]): Promise<void> => {
      if (canMutate && !canMutate()) return
      const current = processingRef.current
      current.count++
      setProcessingState({ count: current.count, revision: current.revision })
      try {
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
          focusEditor()
          return
        }

        setStage((previous) => {
          let bytes = totalBytes(previous.attachments)
          let overSize = false
          let downscaled = false
          let converted = false
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
          return {
            attachments:
              fits.length > 0
                ? [...previous.attachments, ...fits]
                : previous.attachments,
            sizeNotice: previous.sizeNotice || overSize,
            downscaleNotice: previous.downscaleNotice || downscaled,
            gifConvertedNotice: previous.gifConvertedNotice || converted,
          }
        })
        focusEditor()
      } finally {
        current.count--
        current.revision++
        setProcessingState({ count: current.count, revision: current.revision })
      }
    },
    [uploadAccept, maxUploadSize, focusEditor, canMutate],
  )

  const removeAttachment = useCallback(
    (id: string): void => {
      if (canMutate && !canMutate()) return
      // Removing only lowers the running total, so any prior size-cap notice
      // is now stale — clear it on every removal.
      setStage((previous) => {
        const next = previous.attachments.filter((a) => a.id !== id)
        return {
          attachments: next,
          sizeNotice: false,
          downscaleNotice: next.length > 0 && previous.downscaleNotice,
          gifConvertedNotice: next.length > 0 && previous.gifConvertedNotice,
        }
      })
    },
    [canMutate],
  )

  // DOM nodes of the staged-attachment containers, indexed by position, so a
  // keyboard removal can shift focus to the right sibling afterwards.
  const attachmentRefs = useRef<(HTMLDivElement | null)[]>([])
  // The slot to focus once the post-removal render commits: a numeric index
  // into the shrunken list, or "input" when nothing remains.
  const pendingFocusRef = useRef<number | "input" | null>(null)

  const removeAttachmentByKeyboard = useCallback(
    (index: number): void => {
      if (canMutate && !canMutate()) return
      const nextLen = attachments.length - 1
      // Prefer the next attachment (which slides into `index`); fall back to
      // the new last one when the removed item was itself last.
      pendingFocusRef.current =
        nextLen === 0 ? "input" : Math.min(index, nextLen - 1)
      removeAttachment(attachments[index]!.id)
    },
    [attachments, removeAttachment, canMutate],
  )

  useLayoutEffect(() => {
    attachmentRefs.current.length = attachments.length
    const target = pendingFocusRef.current
    if (target === null) return
    pendingFocusRef.current = null
    if (target === "input") {
      focusEditor()
    } else {
      attachmentRefs.current[target]?.focus()
    }
  }, [attachments, focusEditor])

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

  // Clicking the empty space of the attachments tray focuses the editor
  // (clicks on a thumbnail or its remove button pass through untouched).
  const onAttachmentsMouseDown = useCallback(
    (e: React.MouseEvent<HTMLDivElement>): void => {
      if (e.target === e.currentTarget) {
        e.preventDefault()
        focusEditor()
      }
    },
    [focusEditor],
  )

  const getPayloads = useCallback(() => stagedRef.current.map(toPayload), [])

  const applyPayloads = useCallback(
    (payloads: AttachmentPayload[], mode: "append" | "set"): void => {
      const newFiles = toAttachedFiles(payloads)
      if (mode === "append") {
        setStage((previous) => ({
          ...previous,
          attachments: [...previous.attachments, ...newFiles],
        }))
      } else {
        // "set" replaces the tray wholesale (e.g. ChatMessage re-seeding the
        // edit box from the message's saved attachments) -- any notice from
        // a previous, now-discarded staging session is no longer relevant.
        setStage({
          attachments: newFiles,
          downscaleNotice: false,
          gifConvertedNotice: false,
          sizeNotice: false,
        })
      }
    },
    [],
  )

  const clearAttachments = useCallback(() => {
    setStage((previous) => ({ ...previous, attachments: [] }))
  }, [])

  const resetAll = useCallback(() => {
    setStage({
      attachments: [],
      downscaleNotice: false,
      gifConvertedNotice: false,
      sizeNotice: false,
    })
  }, [])

  return {
    attachments,
    processing: processingState.count > 0,
    isProcessing,
    downscaleNotice,
    gifConvertedNotice,
    sizeNotice,
    fileInputRef,
    attachmentRefs,
    addFiles,
    removeAttachment,
    removeAttachmentByKeyboard,
    onPaste,
    onDrop,
    onFilePick,
    onAttachmentsMouseDown,
    getPayloads,
    applyPayloads,
    clearAttachments,
    resetAll,
  }
}
