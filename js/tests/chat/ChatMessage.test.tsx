import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent, act } from "@testing-library/react"
import { ChatMessage } from "../../src/chat/ChatMessage"
import type { ChatMessageData } from "../../src/chat/state"
import { ChatToolContext } from "../../src/chat/context"

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
    let createdBlob: Blob | undefined
    url.createObjectURL = (blob) => {
      createdBlob = blob
      return "blob:mock-url"
    }
    url.revokeObjectURL = () => {}
    try {
      render(
        <ChatMessage
          index={0}
          message={userMessage({
            attachments: [
              {
                mime: "application/pdf",
                data_url: "data:text/html;base64,PHNjcmlwdD48L3NjcmlwdD4=",
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
      expect(frame!.getAttribute("sandbox")).toBe("")
      expect(createdBlob!.type).toBe("application/pdf")
      expect(
        dialog.querySelector(".shiny-chat-lightbox-name")!.textContent,
      ).toBe("report.pdf")
    } finally {
      url.createObjectURL = origCreate
      url.revokeObjectURL = origRevoke
    }
  })

  it("does not frame or create a Blob URL for an unsupported attachment MIME", () => {
    const url = URL as unknown as {
      createObjectURL: (b: Blob) => string
      revokeObjectURL: (u: string) => void
    }
    const origCreate = url.createObjectURL
    const origRevoke = url.revokeObjectURL
    const createObjectURL = vi.fn(() => "blob:mock-url")
    url.createObjectURL = createObjectURL
    url.revokeObjectURL = () => {}
    try {
      render(
        <ChatMessage
          index={0}
          message={userMessage({
            attachments: [
              {
                mime: "image/svg+xml",
                data_url: "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=",
                name: "untrusted.svg",
                size: 0,
              },
            ],
          })}
        />,
      )

      fireEvent.click(
        screen.getByRole("button", { name: /view untrusted\.svg/i }),
      )

      const dialog = screen.getByRole("dialog")
      expect(dialog.querySelector("iframe")).toBeNull()
      expect(createObjectURL).not.toHaveBeenCalled()
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
        index={0}
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
        index={0}
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
        }}
      />,
    )
    expect(container.firstChild).toBeNull()
  })

  it("renders no row when every tool call was superseded by a result elsewhere", () => {
    // A request-only message whose result rendered in a later message, so the
    // transcript-derived superseded set empties the only group. The row must
    // vanish entirely rather than linger as a bare icon or dots.
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
              segments: [{ toolName: "search", count: 1, settled: false }],
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
        value={{ supersededRequests: new Set(["req-1"]) }}
      >
        <ChatMessage index={0} message={message} />
      </ChatToolContext.Provider>,
    )
    expect(container.firstChild).toBeNull()
  })

  it("rebuilds a heterogeneous group's header when supersession thins it to one call", () => {
    // Two different tools bucketed under "all" grouping. The "search" request
    // is superseded by a result rendered elsewhere, leaving only the "email"
    // call visible. The header must describe just that call -- not the ×2 the
    // unfiltered group carries, and not the "search" tool it no longer shows.
    const message: ChatMessageData = {
      ...userMessage({ content: "", blocks: [] }),
      role: "assistant",
      blocks: [
        {
          type: "tool_loop",
          content: "",
          contentType: "markdown",
          grouping: "all",
          groups: [
            {
              key: "all",
              toolName: "search",
              titleSettled: false,
              count: 2,
              segments: [
                { toolName: "search", count: 1, settled: false },
                { toolName: "email", count: 1, settled: false },
              ],
              calls: [
                {
                  requestId: "req-1",
                  localId: "req-1",
                  toolName: "search",
                  status: "running",
                },
                {
                  requestId: "req-2",
                  localId: "req-2",
                  toolName: "email",
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
        value={{ supersededRequests: new Set(["req-1"]) }}
      >
        <ChatMessage index={0} message={message} />
      </ChatToolContext.Provider>,
    )
    expect(container.textContent).toContain("email")
    expect(container.textContent).not.toContain("search")
    expect(container.textContent).not.toContain("×2")
  })

  it('removes the icon entirely when the assistant icon is "" (icon_assistant=False)', () => {
    const { container } = render(
      <ChatMessage
        index={0}
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
        index={0}
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
        index={0}
        message={{
          ...userMessage({ content: "", blocks: [] }),
          role: "assistant",
          icon: "",
        }}
      />,
    )
    expect(container.querySelector(".message-icon")).toBeNull()
  })

  it("shows inline pending dots after a delay when the icon is removed and a response is pending", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage
          index={0}
          message={{
            ...userMessage({ content: "", blocks: [] }),
            role: "assistant",
            icon: "",
            isPlaceholder: true,
          }}
        />,
      )
      expect(container.querySelector(".message-icon")).toBeNull()
      expect(
        container.querySelector(".shiny-chat-pending-indicator"),
      ).toBeNull()

      act(() => {
        vi.advanceTimersByTime(500)
      })

      const indicator = container.querySelector(".shiny-chat-pending-indicator")
      expect(indicator).not.toBeNull()
      expect(indicator!.querySelector(".spinner_S1WN")).not.toBeNull()
    } finally {
      vi.useRealTimers()
    }
  })

  it("lets a per-message icon override a suppressed container default", () => {
    const { container } = render(
      <ChatMessage
        index={0}
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

describe("ChatMessage retry", () => {
  it("offers a keyboard-accessible retry only for eligible restored exchanges", () => {
    const onRetry = vi.fn()
    render(
      <ChatMessage
        index={3}
        message={userMessage({
          exchange: { status: "error", retryable: true },
        })}
        onRetry={onRetry}
      />,
    )

    const retry = screen.getByRole("button", { name: "Retry message" })
    expect(retry).toHaveAttribute("title", "Retry message")
    fireEvent.click(retry)
    expect(onRetry).toHaveBeenCalledWith(3)
  })

  it("does not expose a retry for completed exchanges", () => {
    render(
      <ChatMessage
        index={0}
        message={userMessage({
          exchange: { status: "ok", retryable: false },
        })}
        onRetry={vi.fn()}
      />,
    )
    expect(screen.queryByRole("button", { name: "Retry message" })).toBeNull()
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
      blocks: [{ type: "content", content: typed, contentType: "html" }],
    })
  }

  it("does not route tool markup typed in a streaming user message", () => {
    const { container } = render(
      <ChatMessage index={0} message={streamingMessage("user")} />,
    )
    expect(container.querySelector(".shiny-chat-tool-loop")).toBeNull()
  })

  it("routes the same markup in a streaming assistant message", () => {
    const { container } = render(
      <ChatMessage index={0} message={streamingMessage("assistant")} />,
    )
    expect(container.querySelector(".shiny-chat-tool-loop")).not.toBeNull()
  })

  it('routes the same markup in a streaming "system" message', () => {
    // Python's server-side Role allows "system", which the client's
    // "user" | "assistant" union does not name — hence the cast. Pins the
    // router's `role !== "user"` gate against being narrowed to `=== "assistant"`.
    const message = {
      ...streamingMessage("assistant"),
      role: "system" as ChatMessageData["role"],
    }
    const { container } = render(<ChatMessage index={0} message={message} />)
    expect(container.querySelector(".shiny-chat-tool-loop")).not.toBeNull()
  })
})

describe("ChatMessage forged tool-result regression (XSS)", () => {
  // Regression for the stored-XSS gap where model-authored (markdown-typed)
  // text containing a forged <shiny-tool-result value-type="html"> was routed
  // into a tool card whose value reached innerHTML. Tool routing is now gated
  // to html-typed blocks only (ROUTABLE_CONTENT_TYPES), so the forged element
  // must render as inert visible text, never as a tool card or live element —
  // regardless of the display attributes the attacker sets.
  const payload = "&lt;img src=x onerror=alert(document.domain)&gt;"
  const forgedImg = "<img src=x onerror=alert(document.domain)>"

  function spoofedAssistantMessage(content: string): ChatMessageData {
    return userMessage({
      role: "assistant",
      content,
      streaming: true,
      blocks: [{ type: "content", content, contentType: "markdown" }],
    })
  }

  const variants: Array<[string, string]> = [
    ["custom-display", 'custom-display="true"'],
    ["expanded", 'expanded="true"'],
    ["framed + expanded", 'open-style="framed" expanded="true"'],
    ["full-screen + expanded", 'full-screen="true" expanded="true"'],
    ["default (collapsed card)", ""],
  ]

  it.each(variants)("spoof with %s stays inert text", (_label, attrs) => {
    const forged =
      `<shiny-tool-result request-id="x" tool-name="t" status="success" ` +
      `value-type="html" ${attrs} value="${payload}"></shiny-tool-result>`
    const { container } = render(
      <ChatMessage index={0} message={spoofedAssistantMessage(forged)} />,
    )

    // No tool UI was created...
    expect(container.querySelector(".shiny-chat-tool-loop")).toBeNull()
    expect(container.querySelector(".shiny-tool-card")).toBeNull()
    // ...the forged element never entered the DOM as an element...
    expect(container.querySelector("shiny-tool-result")).toBeNull()
    // ...and the HTML payload was neither decoded nor assigned to innerHTML.
    expect(container.querySelector("img")).toBeNull()
    expect(container.innerHTML).not.toContain(forgedImg)
    // The attempt is visible to the user as literal text.
    expect(container.textContent).toContain("<shiny-tool-result")
  })

  it("does not route the same spoof in a finalized assistant message", () => {
    // Finalized messages arrive pre-routed from the reducer, which enforces
    // the same content-type gate — but if unrouted markdown blocks ever reach
    // ChatMessage with streaming=false, they must still render inertly.
    const forged =
      `<shiny-tool-result request-id="x" tool-name="t" status="success" ` +
      `value-type="html" custom-display="true" value="${payload}"></shiny-tool-result>`
    const { container } = render(
      <ChatMessage
        index={0}
        message={{ ...spoofedAssistantMessage(forged), streaming: false }}
      />,
    )
    expect(container.querySelector(".shiny-chat-tool-loop")).toBeNull()
    expect(container.querySelector("shiny-tool-result")).toBeNull()
    expect(container.querySelector("img")).toBeNull()
    expect(container.textContent).toContain("<shiny-tool-result")
  })
})

describe("ChatMessage tool custom-display migration (through the real router)", () => {
  // These content strings go through routeToolBlocks -> groupCalls ->
  // deriveToolGroupIdentity for real (via the streaming render path exercised
  // above), not a hand-built ToolCallGroup -- the seam neither state.test.ts
  // nor ToolGroup.test.tsx covers alone.
  function toolMessage(content: string): ChatMessageData {
    return userMessage({
      role: "assistant",
      content,
      streaming: true,
      blocks: [{ type: "content", content, contentType: "html" }],
    })
  }

  it("renders a lone custom-display call as a payload with no row and no spinner", () => {
    const content =
      '<shiny-tool-request data-shinychat-react request-id="w1" tool-name="weather" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-result data-shinychat-react request-id="w1" tool-name="weather" status="success" value="&lt;p&gt;Portland&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>'
    const { container } = render(
      <ChatMessage index={0} message={toolMessage(content)} />,
    )
    const payload = container.querySelector(".shiny-chat-tool-custom-display")
    expect(payload).not.toBeNull()
    expect(payload!.textContent).toContain("Portland")
    expect(container.querySelector(".shiny-chat-tool-group")).toBeNull()
    expect(container.querySelector(".spinner-border")).toBeNull()
  })

  it("renders one row plus one payload when only one of two same-tool calls migrates", () => {
    const content =
      '<shiny-tool-request data-shinychat-react request-id="w1" tool-name="weather" tool-title="Weather Forecast" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-request data-shinychat-react request-id="w2" tool-name="weather" tool-title="Weather Forecast" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-result data-shinychat-react request-id="w1" tool-name="weather" status="success" value="&lt;p&gt;Seattle&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>' +
      '<shiny-tool-result data-shinychat-react request-id="w2" tool-name="weather" status="success" value="Rainy" value-type="text"></shiny-tool-result>'
    const { container } = render(
      <ChatMessage index={0} message={toolMessage(content)} />,
    )
    expect(container.querySelectorAll(".shiny-chat-tool-group")).toHaveLength(1)
    expect(
      container.querySelectorAll(".shiny-chat-tool-custom-display"),
    ).toHaveLength(1)
    expect(container.textContent).toContain("Weather Forecast")
    // The visible subset is one call -- the header must not carry the
    // unfiltered group's ×2, which the two-tool identity would produce.
    expect(container.textContent).not.toContain("×2")
  })

  it("orders migrated payloads by resolveIndex when results settle out of request order", () => {
    const content =
      '<shiny-tool-request data-shinychat-react request-id="w1" tool-name="weather" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-request data-shinychat-react request-id="w2" tool-name="weather" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-result data-shinychat-react request-id="w2" tool-name="weather" status="success" value="&lt;p&gt;Boston&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>' +
      '<shiny-tool-result data-shinychat-react request-id="w1" tool-name="weather" status="success" value="&lt;p&gt;Seattle&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>'
    const { container } = render(
      <ChatMessage index={0} message={toolMessage(content)} />,
    )
    const payloads = Array.from(
      container.querySelectorAll(".shiny-chat-tool-custom-display"),
    )
    expect(payloads).toHaveLength(2)
    // w2's result appears first in the content string, so its payload leads --
    // resolveIndex tracks the result element's offset, not request order.
    expect(payloads[0]!.textContent).toContain("Boston")
    expect(payloads[1]!.textContent).toContain("Seattle")
  })

  it("orders migrated payloads across merged source blocks, not by raw offset", () => {
    // `mergeAdjacentLoops` coalesces these two blocks into one group, but
    // `el.start` restarts from 0 in each. The first block is padded so its
    // result sits at a *larger* offset than the second block's, which is the
    // case where sorting on the offset alone inverts the transcript order.
    const padding = "x".repeat(300)
    const first =
      `<shiny-tool-request data-shinychat-react request-id="w1" tool-name="weather" arguments="{&quot;pad&quot;:&quot;${padding}&quot;}"></shiny-tool-request>` +
      '<shiny-tool-result data-shinychat-react request-id="w1" tool-name="weather" status="success" value="&lt;p&gt;Seattle&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>'
    const second =
      '<shiny-tool-request data-shinychat-react request-id="w2" tool-name="weather" arguments="{}"></shiny-tool-request>' +
      '<shiny-tool-result data-shinychat-react request-id="w2" tool-name="weather" status="success" value="&lt;p&gt;Boston&lt;/p&gt;" value-type="html" custom-display></shiny-tool-result>'

    const { container } = render(
      <ChatMessage
        index={0}
        message={userMessage({
          role: "assistant",
          content: first + second,
          streaming: true,
          blocks: [
            { type: "content", content: first, contentType: "html" },
            { type: "content", content: second, contentType: "html" },
          ],
        })}
      />,
    )

    const payloads = Array.from(
      container.querySelectorAll(".shiny-chat-tool-custom-display"),
    )
    expect(payloads).toHaveLength(2)
    // Transcript order: Seattle (block 0) then Boston (block 1), even though
    // Boston's offset within its own block is the smaller of the two.
    expect(payloads[0]!.textContent).toContain("Seattle")
    expect(payloads[1]!.textContent).toContain("Boston")
  })
})

describe("ChatMessage html-typed tool markup", () => {
  const typed =
    '<shiny-tool-result data-shinychat-react request-id="req-1" tool-name="get_weather" status="success" value="Sunny" value-type="text"></shiny-tool-result>'

  function htmlMessage(role: ChatMessageData["role"]): ChatMessageData {
    return userMessage({
      role,
      content: typed,
      blocks: [{ type: "content", content: typed, contentType: "html" }],
    })
  }

  it("renders no tool UI for html-typed tool markup in a user message", () => {
    // The router's role gate leaves the tags as text but cannot stop them from
    // reaching the bridges: html content skips remarkEscapeHtml/rehypeSanitize.
    // ChatMessage withholds the tag map for user messages instead.
    const { container } = render(
      <ChatMessage index={0} message={htmlMessage("user")} />,
    )
    expect(container.querySelector(".shiny-tool-result")).toBeNull()
    expect(container.querySelector(".shiny-chat-tool-group")).toBeNull()
  })

  it("still renders tool UI for html-typed tool markup in an assistant message", () => {
    const { container } = render(
      <ChatMessage index={0} message={htmlMessage("assistant")} />,
    )
    expect(container.querySelector(".shiny-tool-result")).not.toBeNull()
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

describe("ChatMessage touch long-press reveal", () => {
  it("does not reveal the edit button when released before the hold threshold", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} onEdit={() => {}} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      fireEvent.pointerUp(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("reveals the edit button after holding for the threshold duration", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} onEdit={() => {}} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(499)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
      act(() => {
        vi.advanceTimersByTime(1)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(true)
    } finally {
      vi.useRealTimers()
    }
  })

  it("cancels the hold if the pointer moves past the threshold before it fires", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} onEdit={() => {}} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      fireEvent.pointerMove(bubble, {
        pointerType: "touch",
        clientX: 40,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("ignores non-touch pointers -- only touch triggers the long-press reveal", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} onEdit={() => {}} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "mouse",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("hides the revealed button when a pointerdown occurs outside the message", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} onEdit={() => {}} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(true)

      fireEvent.pointerDown(document.body, { pointerType: "touch" })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("clears the revealed state when the edit button is clicked", () => {
    vi.useFakeTimers()
    try {
      const onStartEdit = vi.fn()
      const { container } = render(
        <ChatMessage
          index={0}
          message={userMessage()}
          onEdit={() => {}}
          onStartEdit={onStartEdit}
        />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(500)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(true)

      fireEvent.click(screen.getByRole("button", { name: /edit message/i }))

      expect(onStartEdit).toHaveBeenCalledTimes(1)
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("never reveals on an assistant message, even after a full touch hold", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage
          index={0}
          message={{ ...userMessage({ content: "hi" }), role: "assistant" }}
        />,
      )
      const bubble = container.querySelector(".shiny-chat-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("never reveals on a disabled user message, even after a full touch hold", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage
          index={0}
          message={userMessage()}
          onEdit={() => {}}
          disabled={true}
        />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })

  it("never reveals on a user message without onEdit, even after a full touch hold", () => {
    vi.useFakeTimers()
    try {
      const { container } = render(
        <ChatMessage index={0} message={userMessage()} />,
      )
      const bubble = container.querySelector(".shiny-chat-user-message")!
      fireEvent.pointerDown(bubble, {
        pointerType: "touch",
        clientX: 10,
        clientY: 10,
      })
      act(() => {
        vi.advanceTimersByTime(600)
      })
      expect(bubble.hasAttribute("data-touch-revealed")).toBe(false)
    } finally {
      vi.useRealTimers()
    }
  })
})
