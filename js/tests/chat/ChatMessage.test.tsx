import { describe, it, expect } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"
import { ChatMessage } from "../../src/chat/ChatMessage"
import type { ChatMessageData } from "../../src/chat/state"
import { ChatToolContext } from "../../src/chat/context"

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
    render(<ChatMessage message={userMessage()} />)
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
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
          isPlaceholder: true,
        }}
      />,
    )
    const icon = container.querySelector(".message-icon")
    expect(icon!.querySelector(".spinner_S1WN")).not.toBeNull()
  })

  it("still shows the loading dots for an empty streaming message", () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
          streaming: true,
        }}
      />,
    )
    const icon = container.querySelector(".message-icon")
    expect(icon!.querySelector(".spinner_S1WN")).not.toBeNull()
  })

  it("renders no row for a settled message with nothing to show", () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
        }}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders no row when every tool call was superseded by a result elsewhere", () => {
    // A request-only message whose result rendered in a later message: the
    // request is hidden via hide_tool_request, emptying the only group. The row
    // must vanish entirely rather than linger as a bare icon or dots.
    const message: ChatMessageData = {
      ...userMessage({ content: "", blocks: [] }),
      role: "assistant",
      blocks: [
        {
          type: "tool_loop",
          content: "",
          contentType: "markdown",
          grouping: "tool",
          groups: [
            {
              key: "tool:search",
              toolName: "search",
              titleSettled: false,
              count: 1,
              calls: [
                {
                  requestId: "req-1",
                  localId: "req-1",
                  toolName: "search",
                  status: "running",
                },
              ],
            },
          ],
        },
      ],
    }
    const { container } = render(
      <ChatToolContext.Provider
        value={{ hiddenToolRequests: new Set(["req-1"]) }}
      >
        <ChatMessage message={message} />
      </ChatToolContext.Provider>,
    )
    expect(container.firstChild).toBeNull()
  })

  it('removes the icon entirely when the assistant icon is "" (icon_assistant=False)', () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "hello" }),
          role: "assistant",
          icon: "",
        }}
      />,
    )
    expect(container.querySelector(".message-icon")).toBeNull()
  })

  it('removes the icon via the container default (iconAssistant="")', () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "hello" }),
          role: "assistant",
        }}
        iconAssistant=""
      />,
    )
    expect(container.querySelector(".message-icon")).toBeNull()
  })

  it("suppresses the loading dots too when the icon is removed", () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
          icon: "",
        }}
      />,
    )
    expect(container.querySelector(".message-icon")).toBeNull()
  })

  it("lets a per-message icon override a suppressed container default", () => {
    const { container } = render(
      <ChatMessage
        message={{
          ...userMessage({ content: "hello" }),
          role: "assistant",
          icon: "<span class='custom-icon'>x</span>",
        }}
        iconAssistant=""
      />,
    )
    const icon = container.querySelector(".message-icon")
    expect(icon).not.toBeNull()
    expect(icon!.querySelector(".custom-icon")).not.toBeNull()
  })

  it("traps focus inside the lightbox", () => {
    render(
      <ChatMessage
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

describe("ChatMessage streaming tool routing", () => {
  const typed =
    '<shiny-tool-result data-shinychat-react request-id="req-1" tool-name="get_weather" status="success" value="Sunny" value-type="text"></shiny-tool-result>'

  function streamingMessage(role: ChatMessageData["role"]): ChatMessageData {
    return userMessage({
      role,
      content: typed,
      streaming: true,
      blocks: [{ type: "content", content: typed, contentType: "markdown" }],
    })
  }

  it("does not route tool markup typed in a streaming user message", () => {
    const { container } = render(
      <ChatMessage message={streamingMessage("user")} />,
    )
    expect(container.querySelector(".shinychat-tool-loop")).toBeNull()
  })

  it("routes the same markup in a streaming assistant message", () => {
    const { container } = render(
      <ChatMessage message={streamingMessage("assistant")} />,
    )
    expect(container.querySelector(".shinychat-tool-loop")).not.toBeNull()
  })

  it('routes the same markup in a streaming "system" message', () => {
    // Python's server-side Role allows "system", which the client's
    // "user" | "assistant" union does not name — hence the cast. Pins the
    // router's `role !== "user"` gate against being narrowed to `=== "assistant"`.
    const message = {
      ...streamingMessage("assistant"),
      role: "system" as ChatMessageData["role"],
    }
    const { container } = render(<ChatMessage message={message} />)
    expect(container.querySelector(".shinychat-tool-loop")).not.toBeNull()
  })
})
