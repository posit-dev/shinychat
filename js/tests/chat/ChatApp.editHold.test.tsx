import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  act,
  createEvent,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import { getHistoryStore } from "../../src/chat/historyStore"
import {
  processFile,
  PASTE_AS_FILE_MIN_CHARS,
} from "../../src/chat/attachments"
import type { ChatAction } from "../../src/transport/types"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

vi.mock("../../src/chat/attachments", async (original) => {
  const actual = await original<typeof import("../../src/chat/attachments")>()
  return { ...actual, processFile: vi.fn(actual.processFile) }
})

const attachment = {
  mime: "image/png",
  data_url: "data:image/png;base64,AAA",
  name: "original.png",
  size: 3,
}
let sequence = 0

beforeEach(() => {
  installShinyWindowStub()
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
})

function setup(
  protocol: "completion-v2" | "completion-v1" | undefined,
  uploadAccept = ["image/png"],
) {
  const id = `edit-hold-${++sequence}`
  const transport = createMockTransport()
  const view = render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId={id}
      inputId={`${id}-input`}
      enableUpload
      uploadAccept={uploadAccept}
      initialMessages={[
        {
          id: "original",
          role: "user",
          content: "original text",
          streaming: false,
          blocks: [
            {
              type: "content",
              content: "original text",
              contentType: "markdown",
            },
          ],
          attachments: [attachment],
        },
      ]}
    />,
  )
  const fire = (action: ChatAction) => act(() => transport.fire(id, action))
  fire({
    type: "history_update",
    enabled: true,
    conversations: [],
    active_id: "conv",
    transition_protocol: protocol,
  })
  fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
  const editor = screen.getByPlaceholderText(
    "Edit message",
  ) as HTMLTextAreaElement
  const editBox = editor.closest(".shiny-chat-edit-wrap") as HTMLElement
  fireEvent.change(editor, { target: { value: "my revised draft" } })
  const submit = (via: "keyboard" | "button") => {
    if (via === "keyboard") fireEvent.keyDown(editor, { key: "Enter" })
    else
      fireEvent.click(
        within(editBox).getByRole("button", { name: "Save and resend" }),
      )
    return vi.mocked(transport.sendMessageEdit).mock.calls.at(-1)?.[4] as string
  }
  return { id, transport, fire, editor, editBox, submit, ...view }
}

function reject(requestId: string): ChatAction {
  return { type: "history_transition_rejected", requestId, reason: "busy" }
}

describe("completion-v2 edit admission", () => {
  it.each(["keyboard", "button"] as const)(
    "keeps the same draft mounted and locked after %s submit",
    (via) => {
      const { editor, editBox, submit, transport } = setup("completion-v2")
      const requestId = submit(via)
      expect(requestId).toEqual(expect.any(String))
      expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
      expect(editor).toHaveValue("my revised draft")
      expect(editor).toHaveAttribute("readonly")
      expect(
        within(editBox).getByRole("button", { name: "Save and resend" }),
      ).toBeDisabled()
      expect(
        within(editBox).getByRole("button", { name: "Cancel" }),
      ).toBeDisabled()
      expect(
        within(editBox).getByRole("button", { name: "Remove original.png" }),
      ).toBeDisabled()
      expect(
        within(editBox).getByRole("button", { name: "Attach file" }),
      ).toBeDisabled()
      expect(transport.sendMessageEdit).toHaveBeenCalledWith(
        expect.any(String),
        0,
        "my revised draft",
        [attachment],
        requestId,
      )

      fireEvent.keyDown(editor, { key: "Enter" })
      fireEvent.keyDown(editor, { key: "Escape" })
      fireEvent.change(editor, { target: { value: "overwritten" } })
      fireEvent.click(
        within(editBox).getByRole("button", { name: "Remove original.png" }),
      )
      const dropZone = editBox.querySelector(".shiny-chat-edit-box")!
      const drop = createEvent.drop(dropZone)
      Object.defineProperty(drop, "dataTransfer", {
        value: { files: [new File(["new"], "new.png", { type: "image/png" })] },
      })
      fireEvent(dropZone, drop)
      expect(drop.defaultPrevented).toBe(true)
      const paste = createEvent.paste(editor)
      Object.defineProperty(paste, "clipboardData", {
        value: { items: [], getData: () => "unwanted paste" },
      })
      fireEvent(editor, paste)
      expect(paste.defaultPrevented).toBe(true)
      const attachmentPreview = within(editBox).getByLabelText(
        "Attachment: original.png",
      )
      fireEvent.keyDown(attachmentPreview, { key: "Delete", code: "Delete" })
      expect(transport.sendMessageEdit).toHaveBeenCalledTimes(1)
      expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
      expect(editor).toHaveValue("my revised draft")
      expect(
        within(editBox).getByRole("button", { name: "Remove original.png" }),
      ).toBeInTheDocument()
    },
  )

  it.each(["rejected", "complete"] as const)(
    "ignores stale events and unlocks the mounted draft on matching %s",
    (kind) => {
      const { id, fire, editor, editBox, submit, transport } =
        setup("completion-v2")
      const requestId = submit("keyboard")
      fire(reject("stale"))
      fire({ type: "history_transition_complete", requestId: "stale" })
      expect(getHistoryStore(id).getSnapshot().historyTransitionPending).toBe(
        requestId,
      )
      expect(editor).toHaveAttribute("readonly")
      fire(
        kind === "rejected"
          ? reject(requestId)
          : { type: "history_transition_complete", requestId },
      )
      expect(
        getHistoryStore(id).getSnapshot().historyTransitionPending,
      ).toBeNull()
      expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
      expect(editor).toHaveValue("my revised draft")
      expect(editor).not.toHaveAttribute("readonly")
      expect(
        within(editBox).getByRole("button", { name: "Remove original.png" }),
      ).toBeEnabled()
      fireEvent.change(editor, { target: { value: "retry draft" } })
      submit("button")
      expect(transport.sendMessageEdit).toHaveBeenCalledTimes(2)
      expect(transport.sendMessageEdit).toHaveBeenLastCalledWith(
        id,
        0,
        "retry draft",
        [attachment],
        expect.any(String),
      )
    },
  )

  it("keeps the draft mounted if history becomes read-only before rejection", () => {
    const { fire, editor, editBox, submit } = setup("completion-v2")
    const requestId = submit("keyboard")
    fire({
      type: "history_update",
      enabled: true,
      conversations: [],
      active_id: "conv",
      active_read_only: true,
      transition_protocol: "completion-v2",
    })
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    fire(reject(requestId))
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(editor).not.toHaveAttribute("readonly")
    expect(
      within(editBox).getByRole("button", { name: "Remove original.png" }),
    ).toBeEnabled()
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeDisabled()
    expect(
      within(editBox).getByRole("button", { name: "Cancel" }),
    ).toBeEnabled()
  })

  it("retains newly uploaded attachments along with the original on rejection", async () => {
    const { id, fire, editor, editBox, submit, transport } =
      setup("completion-v2")
    vi.mocked(processFile).mockResolvedValueOnce({
      file: {
        id: "new",
        type: "image/png",
        family: "image",
        dataUrl: "data:image/png;base64,BBB",
        name: "new.png",
        size: 3,
      },
      wasDownscaled: false,
      wasConverted: false,
    })
    await act(async () => {
      fireEvent.change(editBox.querySelector("input[type=file]")!, {
        target: {
          files: [new File(["new"], "new.png", { type: "image/png" })],
        },
      })
    })
    const requestId = submit("button")
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      id,
      0,
      "my revised draft",
      [
        attachment,
        {
          mime: "image/png",
          data_url: "data:image/png;base64,BBB",
          name: "new.png",
          size: 3,
        },
      ],
      requestId,
    )
    fire(reject(requestId))
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(
      within(editBox).getByRole("button", { name: "Remove original.png" }),
    ).toBeEnabled()
    expect(
      within(editBox).getByRole("button", { name: "Remove new.png" }),
    ).toBeEnabled()
  })

  it("retains an attachments-only edit when it is rejected", () => {
    const { id, fire, editor, editBox, submit, transport } =
      setup("completion-v2")
    fireEvent.change(editor, { target: { value: "" } })
    const requestId = submit("keyboard")
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      id,
      0,
      "",
      [attachment],
      requestId,
    )
    fire(reject(requestId))
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("")
    expect(
      within(editBox).getByRole("button", { name: "Remove original.png" }),
    ).toBeEnabled()
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeEnabled()
  })

  it("ignores an older request's rejection, completion, and projection after retry", () => {
    const { id, fire, editor, submit } = setup("completion-v2")
    const firstId = submit("button")
    fire(reject(firstId))
    fireEvent.change(editor, { target: { value: "second draft" } })
    const secondId = submit("button")
    expect(secondId).not.toBe(firstId)
    fire(reject(firstId))
    fire({ type: "history_transition_complete", requestId: firstId })
    fire({
      type: "history_edit_projection",
      requestId: firstId,
      index: 0,
      content: "stale replacement",
      attachments: [],
      exchange_id: "stale",
    })
    expect(getHistoryStore(id).getSnapshot().historyTransitionPending).toBe(
      secondId,
    )
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("second draft")
    expect(editor).toHaveAttribute("readonly")
    fire(reject(secondId))
    expect(editor).not.toHaveAttribute("readonly")
  })

  it("waits for an in-flight upload before submitting and retains it on rejection", async () => {
    const { id, editor, editBox, submit, fire, transport } =
      setup("completion-v2")
    let finish!: (value: Awaited<ReturnType<typeof processFile>>) => void
    vi.mocked(processFile).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    act(() => {
      fireEvent.change(editBox.querySelector("input[type=file]")!, {
        target: {
          files: [new File(["new"], "late.png", { type: "image/png" })],
        },
      })
      // The guard must work before React renders the disabled button.
      submit("keyboard")
      submit("button")
    })
    expect(transport.sendMessageEdit).not.toHaveBeenCalled()
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeDisabled()
    await act(async () => {
      finish({
        file: {
          id: "late",
          type: "image/png",
          family: "image",
          dataUrl: "data:image/png;base64,AAA",
          name: "late.png",
          size: 3,
        },
        wasDownscaled: false,
        wasConverted: false,
      })
      await Promise.resolve()
      // Conversion has finished, but its attachment has not committed yet.
      submit("keyboard")
      expect(transport.sendMessageEdit).not.toHaveBeenCalled()
    })
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeEnabled()
    const requestId = submit("keyboard")
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      id,
      0,
      "my revised draft",
      [
        attachment,
        {
          mime: "image/png",
          data_url: "data:image/png;base64,AAA",
          name: "late.png",
          size: 3,
        },
      ],
      requestId,
    )
    fire(reject(requestId))
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(
      within(editBox).getByRole("button", { name: "Remove original.png" }),
    ).toBeEnabled()
    expect(
      within(editBox).getByRole("button", { name: "Remove late.png" }),
    ).toBeEnabled()
  })

  it("waits for every concurrent upload and releases the guard after failures", async () => {
    const { id, editor, editBox, submit, transport } = setup("completion-v2")
    let finishFirst!: (value: Awaited<ReturnType<typeof processFile>>) => void
    let failSecond!: (reason: Error) => void
    vi.mocked(processFile)
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finishFirst = resolve
          }),
      )
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            failSecond = reject
          }),
      )
    const input = editBox.querySelector("input[type=file]")!
    fireEvent.change(input, {
      target: { files: [new File(["a"], "first.png", { type: "image/png" })] },
    })
    fireEvent.change(input, {
      target: { files: [new File(["b"], "second.png", { type: "image/png" })] },
    })
    await act(async () => {
      finishFirst({
        file: {
          id: "first",
          type: "image/png",
          family: "image",
          dataUrl: "data:image/png;base64,QQ==",
          name: "first.png",
          size: 1,
        },
        wasDownscaled: false,
        wasConverted: false,
      })
    })
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeDisabled()
    submit("keyboard")
    expect(transport.sendMessageEdit).not.toHaveBeenCalled()
    expect(editor).toHaveValue("my revised draft")
    await act(async () => {
      failSecond(new Error("reader failed"))
    })
    expect(
      within(editBox).getByRole("button", { name: "Save and resend" }),
    ).toBeEnabled()
    const requestId = submit("button")
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      id,
      0,
      "my revised draft",
      [
        attachment,
        {
          mime: "image/png",
          data_url: "data:image/png;base64,QQ==",
          name: "first.png",
          size: 1,
        },
      ],
      requestId,
    )
  })

  it("keeps a long pasted text attachment until it can be submitted", async () => {
    const { id, fire, editor, editBox, submit, transport } = setup(
      "completion-v2",
      ["image/png", "text/plain"],
    )
    const text = "x".repeat(PASTE_AS_FILE_MIN_CHARS + 1)
    let finish!: (value: Awaited<ReturnType<typeof processFile>>) => void
    vi.mocked(processFile).mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    const paste = createEvent.paste(editor)
    Object.defineProperty(paste, "clipboardData", {
      value: { items: [], getData: () => text },
    })
    fireEvent(editor, paste)
    expect(paste.defaultPrevented).toBe(true)
    const pastedFile = vi.mocked(processFile).mock.calls.at(-1)?.[0]
    expect(pastedFile).toMatchObject({
      name: "Pasted Text",
      type: "text/plain",
      size: text.length,
    })
    const fileText = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result as string)
      reader.onerror = () => reject(reader.error)
      reader.readAsText(pastedFile!)
    })
    expect(fileText).toBe(text)
    submit("keyboard")
    expect(transport.sendMessageEdit).not.toHaveBeenCalled()
    expect(editor).toHaveValue("my revised draft")
    await act(async () => {
      finish({
        file: {
          id: "pasted",
          type: "text/plain",
          family: "text",
          dataUrl: `data:text/plain;base64,${btoa(text)}`,
          name: "Pasted Text",
          size: text.length,
        },
        wasDownscaled: false,
        wasConverted: false,
      })
    })
    const requestId = submit("button")
    expect(transport.sendMessageEdit).toHaveBeenCalledWith(
      id,
      0,
      "my revised draft",
      [
        attachment,
        {
          mime: "text/plain",
          data_url: `data:text/plain;base64,${btoa(text)}`,
          name: "Pasted Text",
          size: text.length,
        },
      ],
      requestId,
    )
    fire(reject(requestId))
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(
      within(editBox).getByRole("button", { name: "Remove Pasted Text" }),
    ).toBeEnabled()
  })

  it("accepts only a matching projection and replaces the draft with server content", () => {
    const { fire, editor, submit, transport } = setup("completion-v2")
    fire({
      type: "message",
      message: {
        role: "user",
        segments: [{ content: "another user", content_type: "markdown" }],
      },
    })
    const requestId = submit("keyboard")
    const projection = {
      type: "history_edit_projection" as const,
      requestId: "stale",
      index: 0,
      content: "server replacement",
      attachments: [attachment],
      exchange_id: "replacement",
    }
    fire(projection)
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    fire({ ...projection, requestId, index: 1 })
    expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
    expect(editor).toHaveValue("my revised draft")
    expect(screen.getByText("another user")).toBeInTheDocument()
    warn.mockRestore()
    fire({ ...projection, requestId })
    expect(screen.queryByPlaceholderText("Edit message")).toBeNull()
    expect(screen.getByText("server replacement")).toBeInTheDocument()
    expect(transport.sendInput).not.toHaveBeenCalled()
  })

  it.each([undefined, "completion-v1"] as const)(
    "waits for file processing before a legacy %s edit",
    async (protocol) => {
      const { id, editor, editBox, submit, transport } = setup(protocol)
      let finish!: (value: Awaited<ReturnType<typeof processFile>>) => void
      vi.mocked(processFile).mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve
          }),
      )
      fireEvent.change(editBox.querySelector("input[type=file]")!, {
        target: {
          files: [new File(["x"], "extra.png", { type: "image/png" })],
        },
      })
      submit("keyboard")
      expect(transport.sendMessageEdit).not.toHaveBeenCalled()
      expect(screen.getByPlaceholderText("Edit message")).toBe(editor)
      await act(async () => {
        finish({
          file: {
            id: "extra",
            type: "image/png",
            family: "image",
            dataUrl: "data:image/png;base64,eA==",
            name: "extra.png",
            size: 1,
          },
          wasDownscaled: false,
          wasConverted: false,
        })
      })
      submit("button")
      expect(screen.queryByPlaceholderText("Edit message")).toBeNull()
      expect(transport.sendMessageEdit).toHaveBeenCalledWith(
        id,
        0,
        "my revised draft",
        [
          attachment,
          {
            mime: "image/png",
            data_url: "data:image/png;base64,eA==",
            name: "extra.png",
            size: 1,
          },
        ],
      )
    },
  )

  it.each([undefined, "completion-v1"] as const)(
    "keeps legacy %s submission optimistic",
    (protocol) => {
      const { submit, transport } = setup(protocol)
      submit("keyboard")
      expect(screen.queryByPlaceholderText("Edit message")).toBeNull()
      expect(transport.sendMessageEdit).toHaveBeenCalledWith(
        expect.any(String),
        0,
        "my revised draft",
        [attachment],
      )
    },
  )
})
