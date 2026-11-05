import { it, expect, vi } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import { processFile } from "../../src/chat/attachments"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

vi.mock("../../src/chat/attachments", async (original) => {
  const actual = await original<typeof import("../../src/chat/attachments")>()
  return { ...actual, processFile: vi.fn(actual.processFile) }
})

it("retains a real Tiptap edit on Enter and rejects document changes until rejection", () => {
  installShinyWindowStub()
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  const transport = createMockTransport()
  render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId="real-edit-hold"
      inputId="real-edit-input"
      initialMessages={[
        {
          id: "original",
          role: "user",
          content: "original",
          streaming: false,
          blocks: [
            { type: "content", content: "original", contentType: "markdown" },
          ],
        },
      ]}
    />,
  )
  act(() => {
    transport.fire("real-edit-hold", {
      type: "history_update",
      enabled: true,
      conversations: [],
      active_id: "conv",
      transition_protocol: "completion-v2",
    })
  })
  fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
  const editor = document.querySelector(
    ".shiny-chat-edit-box [role=textbox]",
  ) as HTMLElement & {
    editor: { commands: { insertContent: (text: string) => boolean } }
  }
  expect(editor.textContent).toBe("original")
  act(() => editor.editor.commands.insertContent(" changed"))
  const draft = editor.textContent
  expect(draft).toContain("changed")
  act(() => {
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter" })
    // React has not rendered the pending state yet; the live guard must
    // already reject edits and cancellation.
    editor.editor.commands.insertContent(" forbidden-before-render")
    fireEvent.keyDown(editor, { key: "Escape", code: "Escape" })
  })
  expect(transport.sendMessageEdit).toHaveBeenCalledTimes(1)
  expect(editor).toBe(
    document.querySelector(".shiny-chat-edit-box [role=textbox]"),
  )
  expect(editor.textContent).toBe(draft)
  expect(editor).toHaveAttribute("aria-readonly", "true")
  act(() => editor.editor.commands.insertContent(" forbidden"))
  expect(editor.textContent).toBe(draft)
  fireEvent.keyDown(editor, { key: "Enter", code: "Enter" })
  expect(transport.sendMessageEdit).toHaveBeenCalledTimes(1)
  const requestId = vi.mocked(transport.sendMessageEdit).mock.calls[0]![4]!
  act(() => {
    transport.fire("real-edit-hold", {
      type: "history_transition_rejected",
      requestId,
      reason: "busy",
    })
  })
  expect(editor).not.toHaveAttribute("aria-readonly")
  expect(editor.textContent).toBe(draft)
  act(() => editor.editor.commands.insertContent(" allowed"))
  expect(editor.textContent).toContain("allowed")
})

it("does not clear a real Tiptap edit when Enter races an in-flight upload", async () => {
  installShinyWindowStub()
  vi.stubGlobal("matchMedia", () => ({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
  const transport = createMockTransport()
  const { container } = render(
    <ChatApp
      transport={transport}
      shinyLifecycle={createMockShinyLifecycle()}
      elementId="real-edit-processing"
      inputId="real-edit-processing-input"
      enableUpload
      uploadAccept={["image/png"]}
      initialMessages={[
        {
          id: "original",
          role: "user",
          content: "original draft",
          streaming: false,
          blocks: [
            {
              type: "content",
              content: "original draft",
              contentType: "markdown",
            },
          ],
        },
      ]}
    />,
  )
  act(() => {
    transport.fire("real-edit-processing", {
      type: "history_update",
      enabled: true,
      conversations: [],
      active_id: "conv",
      transition_protocol: "completion-v2",
    })
  })
  fireEvent.click(screen.getByRole("button", { name: "Edit message" }))
  const editor = container.querySelector(".shiny-chat-edit-box [role=textbox]")!
  const fileInput = container.querySelector(
    ".shiny-chat-edit-box input[type=file]",
  )!
  let finish!: (value: Awaited<ReturnType<typeof processFile>>) => void
  vi.mocked(processFile).mockImplementationOnce(
    () =>
      new Promise((resolve) => {
        finish = resolve
      }),
  )
  act(() => {
    fireEvent.change(fileInput, {
      target: { files: [new File(["x"], "late.png", { type: "image/png" })] },
    })
    fireEvent.keyDown(editor, { key: "Enter", code: "Enter" })
  })
  expect(transport.sendMessageEdit).not.toHaveBeenCalled()
  expect(editor).toHaveTextContent("original draft")
  expect(screen.getByRole("button", { name: "Save and resend" })).toBeDisabled()
  await act(async () => {
    finish({
      file: {
        id: "late",
        type: "image/png",
        family: "image",
        dataUrl: "data:image/png;base64,eA==",
        name: "late.png",
        size: 1,
      },
      wasDownscaled: false,
      wasConverted: false,
    })
  })
  fireEvent.keyDown(editor, { key: "Enter", code: "Enter" })
  expect(transport.sendMessageEdit).toHaveBeenCalledWith(
    "real-edit-processing",
    0,
    "original draft",
    [
      {
        mime: "image/png",
        data_url: "data:image/png;base64,eA==",
        name: "late.png",
        size: 1,
      },
    ],
    expect.any(String),
  )
  expect(editor).toHaveTextContent("original draft")
})
