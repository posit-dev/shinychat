import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatMessage } from "../../src/chat/ChatMessage"
import type { ChatMessageData } from "../../src/chat/state"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

function userMessage(
  overrides: Partial<ChatMessageData> = {},
): ChatMessageData {
  return {
    id: "m1",
    role: "user",
    content: "hi",
    streaming: false,
    blocks: [{ type: "content", content: "hi", contentType: "markdown" }],
    ...overrides,
  }
}

const imageAttachment = (src: string, mime = "image/png") => ({
  mime,
  data_url: src,
  name: "pic",
  size: 0,
})

describe("ChatMessage attachments", () => {
  it("renders an <img> for each attached image", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [
            imageAttachment("data:image/png;base64,AAA"),
            imageAttachment("data:image/jpeg;base64,BBB", "image/jpeg"),
          ],
        })}
      />,
    )
    const imgs = screen.getAllByRole("img")
    expect(imgs).toHaveLength(2)
    expect(imgs[0]!.getAttribute("src")).toBe("data:image/png;base64,AAA")
  })

  it("opens a lightbox with the full image when a thumbnail is clicked", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
      />,
    )
    expect(screen.queryByRole("dialog")).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: /view pic/i }))

    const dialog = screen.getByRole("dialog")
    const full = dialog.querySelector(".shiny-chat-lightbox-img")
    expect(full).not.toBeNull()
    expect(full!.getAttribute("src")).toBe("data:image/png;base64,AAA")
    // The file name is shown beneath the preview.
    expect(dialog.querySelector(".shiny-chat-lightbox-name")!.textContent).toBe(
      "pic",
    )

    fireEvent.click(screen.getByRole("button", { name: /close preview/i }))
    expect(screen.queryByRole("dialog")).toBeNull()
  })

  it("opens a PDF in the lightbox with an iframe and the filename", () => {
    // jsdom doesn't implement URL.createObjectURL; stub it for the iframe src.
    const url = URL as unknown as {
      createObjectURL: (b: Blob) => string
      revokeObjectURL: (u: string) => void
    }
    const origCreate = url.createObjectURL
    const origRevoke = url.revokeObjectURL
    url.createObjectURL = () => "blob:mock-url"
    url.revokeObjectURL = () => {}
    try {
      render(
        <ChatMessage
          index={0}
          message={userMessage({
            attachments: [
              {
                mime: "application/pdf",
                data_url: "data:application/pdf;base64,JVBERi0xLjQK",
                name: "report.pdf",
                size: 0,
              },
            ],
          })}
        />,
      )
      fireEvent.click(screen.getByRole("button", { name: /view report\.pdf/i }))
      const dialog = screen.getByRole("dialog")
      const frame = dialog.querySelector("iframe")
      expect(frame).not.toBeNull()
      expect(frame!.getAttribute("src")).toBe("blob:mock-url")
      expect(
        dialog.querySelector(".shiny-chat-lightbox-name")!.textContent,
      ).toBe("report.pdf")
    } finally {
      url.createObjectURL = origCreate
      url.revokeObjectURL = origRevoke
    }
  })

  it("orders attachments by role (user: above text, assistant: below)", () => {
    const atts = [imageAttachment("data:image/png;base64,AAA")]

    const { container: userC } = render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "see this", attachments: atts })}
      />,
    )
    const userContent = userC.querySelector(".shiny-chat-message-content")!
    const userKids = Array.from(userContent.children)
    const userAttIdx = userKids.findIndex((el) =>
      el.classList.contains("shiny-chat-message-attachments"),
    )
    // User: attachments come before the markdown content block.
    expect(userAttIdx).toBe(0)

    const { container: botC } = render(
      <ChatMessage
        index={0}
        message={{
          ...userMessage({ content: "here it is", attachments: atts }),
          role: "assistant",
        }}
      />,
    )
    const botContent = botC.querySelector(".shiny-chat-message-content")!
    const botKids = Array.from(botContent.children)
    const botAttIdx = botKids.findIndex((el) =>
      el.classList.contains("shiny-chat-message-attachments"),
    )
    // Assistant: attachments come after the content.
    expect(botAttIdx).toBe(botKids.length - 1)
    expect(botAttIdx).toBeGreaterThan(0)
  })

  it("renders no attachments when none present", () => {
    render(<ChatMessage index={0} message={userMessage()} />)
    expect(screen.queryByRole("img")).toBeNull()
    expect(
      document.querySelector(".shiny-chat-message-attachment-chip"),
    ).toBeNull()
  })

  it("renders attachments on assistant messages too", () => {
    // Attachments are role-agnostic: e.g. a tool/assistant turn returning a
    // generated image via append_message(role="assistant", attachments=[...]).
    render(
      <ChatMessage
        index={0}
        message={{
          ...userMessage({
            attachments: [imageAttachment("data:image/png;base64,AAA")],
          }),
          role: "assistant",
        }}
      />,
    )
    expect(screen.queryByRole("img")).not.toBeNull()
  })

  it("renders a PDF attachment as a chip with its filename", () => {
    const { container } = render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [
            {
              mime: "application/pdf",
              data_url: "data:application/pdf;base64,AAA",
              name: "report.pdf",
              size: 0,
            },
          ],
        })}
      />,
    )
    const chip = container.querySelector(".shiny-chat-message-attachment-chip")
    expect(chip).not.toBeNull()
    expect(chip!.textContent).toContain("report.pdf")
    expect(container.querySelector("img.shiny-chat-message-image")).toBeNull()
  })

  it("renders a text attachment as a preview card with no remove button", () => {
    const body = "# Project Notes\nbody line"
    const dataUrl = `data:text/markdown;base64,${btoa(body)}`
    const { container } = render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [
            {
              mime: "text/markdown",
              data_url: dataUrl,
              name: "notes.md",
              size: 0,
            },
          ],
        })}
      />,
    )
    const card = container.querySelector(".shiny-chat-text-preview")
    expect(card).not.toBeNull()
    expect(card!.textContent).toContain("# Project Notes")
    expect(card!.textContent).toContain("notes.md")
    expect(card!.querySelector("button")).toBeNull()
  })

  it("shows the assistant icon (not the loading dots) for an attachment-only response", () => {
    const { container } = render(
      <ChatMessage
        index={0}
        message={{
          ...userMessage({
            content: "",
            blocks: [],
            attachments: [imageAttachment("data:image/png;base64,AAA")],
          }),
          role: "assistant",
        }}
      />,
    )
    const icon = container.querySelector(".message-icon")
    expect(icon).not.toBeNull()
    // Resolved assistant icon, not the still-loading spinner.
    expect(icon!.querySelector(".bi-robot")).not.toBeNull()
    expect(icon!.querySelector(".spinner_S1WN")).toBeNull()
  })

  it("still shows the loading dots for an empty assistant placeholder", () => {
    const { container } = render(
      <ChatMessage
        index={0}
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
        }}
      />,
    )
    const icon = container.querySelector(".message-icon")
    expect(icon!.querySelector(".spinner_S1WN")).not.toBeNull()
  })

  it("traps focus inside the lightbox", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /view pic/i }))
    const dialog = screen.getByRole("dialog")

    // The lightbox has two focusable elements: the close button and the image.
    // Focus should be inside the dialog after opening.
    const closeBtn = screen.getByRole("button", { name: /close preview/i })
    expect(dialog.contains(document.activeElement)).toBe(true)

    // Tab from the last focusable element should wrap to the first.
    closeBtn.focus()
    fireEvent.keyDown(dialog, { key: "Tab" })
    expect(dialog.contains(document.activeElement)).toBe(true)

    // Shift+Tab from the first focusable element should wrap to the last.
    const focusable = dialog.querySelectorAll<HTMLElement>(
      'button, [tabindex="0"], a[href], input, select, textarea',
    )
    const first = focusable[0]!
    first.focus()
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true })
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it("moves focus into the lightbox on open", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /view pic/i }))
    const dialog = screen.getByRole("dialog")
    expect(dialog.contains(document.activeElement)).toBe(true)
  })

  it("restores focus to the opener when the lightbox closes", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
      />,
    )
    const opener = screen.getByRole("button", { name: /view pic/i })
    opener.focus()

    fireEvent.click(opener)
    fireEvent.click(screen.getByRole("button", { name: /close preview/i }))

    expect(document.activeElement).toBe(opener)
  })

  it("locks body scrolling while the lightbox is open and restores it on close", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
      />,
    )
    const originalOverflow = document.body.style.overflow

    fireEvent.click(screen.getByRole("button", { name: /view pic/i }))
    expect(document.body.style.overflow).toBe("hidden")

    fireEvent.click(screen.getByRole("button", { name: /close preview/i }))
    expect(document.body.style.overflow).toBe(originalOverflow)
  })

  it("opens a lightbox with the full text when a text card is clicked", () => {
    const body = "# Title\n" + "line\n".repeat(400) // longer than the snippet
    const dataUrl = `data:text/markdown;base64,${btoa(body)}`
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          attachments: [
            {
              mime: "text/markdown",
              data_url: dataUrl,
              name: "notes.md",
              size: 0,
            },
          ],
        })}
      />,
    )
    expect(screen.queryByRole("dialog")).toBeNull()

    const card = document.querySelector(".shiny-chat-text-preview")!
    expect(card.getAttribute("role")).toBe("button")
    fireEvent.click(card)

    const dialog = screen.getByRole("dialog")
    const pre = dialog.querySelector(".shiny-chat-lightbox-text")
    expect(pre).not.toBeNull()
    expect(pre!.getAttribute("aria-label")).toBe("notes.md")
    expect(pre!.textContent).toBe(body) // full content, not the truncated snippet
    expect(dialog.querySelector(".shiny-chat-lightbox-name")!.textContent).toBe(
      "notes.md",
    )

    fireEvent.click(screen.getByRole("button", { name: /close preview/i }))
    expect(screen.queryByRole("dialog")).toBeNull()
  })
})

describe("ChatMessage editing", () => {
  it("calls onStartEdit when the edit button is clicked, without entering edit mode itself", () => {
    const onStartEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={() => {}}
        onStartEdit={onStartEdit}
      />,
    )
    expect(screen.queryByRole("textbox", { name: "Chat message" })).toBeNull()

    fireEvent.click(screen.getByRole("button", { name: /edit message/i }))

    expect(onStartEdit).toHaveBeenCalledTimes(1)
    // ChatMessage doesn't manage its own editing state -- the parent decides
    // whether to re-render with isEditing.
    expect(screen.queryByRole("textbox", { name: "Chat message" })).toBeNull()
  })

  it("shows the edit box pre-filled with the message content when isEditing is true", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={() => {}}
        isEditing
      />,
    )
    const editor = screen.getByRole("textbox", {
      name: "Chat message",
    }) as HTMLTextAreaElement
    expect(editor.value).toBe("hello world")
  })

  it("cancels editing on Escape without calling onEdit", () => {
    const onEdit = vi.fn()
    const onCancelEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
        onCancelEdit={onCancelEdit}
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })

    fireEvent.keyDown(editor, { key: "Escape" })

    expect(onCancelEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).not.toHaveBeenCalled()
  })

  it("cancels editing when the Cancel button is clicked, without calling onEdit", () => {
    const onEdit = vi.fn()
    const onCancelEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
        onCancelEdit={onCancelEdit}
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }))

    expect(onCancelEdit).toHaveBeenCalledTimes(1)
    expect(onEdit).not.toHaveBeenCalled()
  })

  it("submits the current content on Enter and calls onEdit then onCancelEdit", () => {
    const onEdit = vi.fn()
    const onCancelEdit = vi.fn()
    render(
      <ChatMessage
        index={2}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
        onCancelEdit={onCancelEdit}
        submitKey="enter"
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "edited content" } })

    fireEvent.keyDown(editor, { key: "Enter" })

    expect(onEdit).toHaveBeenCalledWith(2, "edited content", [])
    expect(onCancelEdit).toHaveBeenCalledTimes(1)
  })

  it("only submits on Mod+Enter (not plain Enter) when submitKey is enter+modifier", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={1}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
        submitKey="enter+modifier"
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "ctrl edited" } })

    fireEvent.keyDown(editor, { key: "Enter" })
    expect(onEdit).not.toHaveBeenCalled()

    fireEvent.keyDown(editor, { key: "Enter", ctrlKey: true })
    expect(onEdit).toHaveBeenCalledWith(1, "ctrl edited", [])
  })

  it("submits via the send button using the current content", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "clicked save" } })

    fireEvent.click(screen.getByRole("button", { name: /save and resend/i }))

    expect(onEdit).toHaveBeenCalledWith(0, "clicked save", [])
  })
})

describe("ChatMessage editing with attachments", () => {
  it("pre-stages the message's existing attachments when edit mode opens", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          content: "hello",
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
        onEdit={() => {}}
        isEditing
        enableUpload
      />,
    )
    expect(
      document.querySelectorAll(".shiny-chat-input-thumbnail"),
    ).toHaveLength(1)
  })

  it("removing the pre-staged attachment and saving sends an empty attachments list", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          content: "hello",
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
        onEdit={onEdit}
        isEditing
        enableUpload
      />,
    )
    fireEvent.click(
      document.querySelector(".shiny-chat-input-thumbnail button")!,
    )
    expect(
      document.querySelectorAll(".shiny-chat-input-thumbnail"),
    ).toHaveLength(0)

    fireEvent.click(screen.getByRole("button", { name: /save and resend/i }))

    expect(onEdit).toHaveBeenCalledWith(0, "hello", [])
  })

  it("allows Enter-to-submit an attachments-only edit (empty text, staged attachment)", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          content: "hello",
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
        onEdit={onEdit}
        isEditing
        enableUpload
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "" } })

    fireEvent.keyDown(editor, { key: "Enter" })

    expect(onEdit).toHaveBeenCalledWith(0, "", [
      imageAttachment("data:image/png;base64,AAA"),
    ])
  })

  it("saving after editing only the text keeps the untouched attachment", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          content: "hello",
          attachments: [imageAttachment("data:image/png;base64,AAA")],
        })}
        onEdit={onEdit}
        isEditing
        enableUpload
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "hello there" } })

    fireEvent.click(screen.getByRole("button", { name: /save and resend/i }))

    expect(onEdit).toHaveBeenCalledWith(0, "hello there", [
      imageAttachment("data:image/png;base64,AAA"),
    ])
  })

  it("shows the attach button in the edit box when enableUpload is true", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello" })}
        onEdit={() => {}}
        isEditing
        enableUpload
      />,
    )
    expect(screen.getByRole("button", { name: /attach file/i })).not.toBeNull()
  })

  it("hides the attach button in the edit box when enableUpload is false", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello" })}
        onEdit={() => {}}
        isEditing
      />,
    )
    expect(screen.queryByRole("button", { name: /attach file/i })).toBeNull()
  })
})

describe("ChatMessage editing is guarded while streaming", () => {
  it("does not call onEdit when disabled and Enter is pressed", () => {
    const onEdit = vi.fn()
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={onEdit}
        isEditing
        disabled
      />,
    )
    const editor = screen.getByRole("textbox", { name: "Chat message" })
    fireEvent.change(editor, { target: { value: "edited while streaming" } })
    fireEvent.keyDown(editor, { key: "Enter" })
    expect(onEdit).not.toHaveBeenCalled()
  })

  it("disables the Save button while disabled, even with editable content", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ content: "hello world" })}
        onEdit={() => {}}
        isEditing
        disabled
      />,
    )
    const saveButton = screen.getByRole("button", {
      name: /save and resend/i,
    }) as HTMLButtonElement
    expect(saveButton.disabled).toBe(true)
  })
})

describe("ChatMessage editing/navigation only apply to user messages", () => {
  it("never renders the edit button on an assistant message, even with onEdit supplied", () => {
    render(
      <ChatMessage
        index={0}
        message={{ ...userMessage({ content: "hi" }), role: "assistant" }}
        onEdit={() => {}}
      />,
    )
    expect(screen.queryByRole("button", { name: /edit message/i })).toBeNull()
  })

  it("never renders sibling nav on an assistant message, even with siblings data", () => {
    render(
      <ChatMessage
        index={0}
        message={{
          ...userMessage({ siblings: { index: 0, total: 2 } }),
          role: "assistant",
        }}
        onNavigate={() => {}}
      />,
    )
    expect(screen.queryByRole("button", { name: /next version/i })).toBeNull()
    expect(
      screen.queryByRole("button", { name: /previous version/i }),
    ).toBeNull()
  })
})

describe("ChatMessage sibling navigation", () => {
  it("calls onNavigate with the index and direction when nav buttons are clicked", () => {
    const onNavigate = vi.fn()
    render(
      <ChatMessage
        index={3}
        message={userMessage({ siblings: { index: 0, total: 2 } })}
        onNavigate={onNavigate}
      />,
    )
    fireEvent.click(screen.getByRole("button", { name: /next version/i }))
    expect(onNavigate).toHaveBeenCalledWith(3, "next")
  })

  it("disables the previous button at the first sibling", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ siblings: { index: 0, total: 2 } })}
        onNavigate={() => {}}
      />,
    )
    expect(
      (
        screen.getByRole("button", {
          name: /previous version/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(
      (
        screen.getByRole("button", {
          name: /next version/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false)
  })

  it("disables the next button at the last sibling", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({ siblings: { index: 1, total: 2 } })}
        onNavigate={() => {}}
      />,
    )
    expect(
      (
        screen.getByRole("button", {
          name: /next version/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true)
    expect(
      (
        screen.getByRole("button", {
          name: /previous version/i,
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(false)
  })
})
