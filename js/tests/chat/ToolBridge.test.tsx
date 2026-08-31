import { describe, it, expect, beforeEach, vi } from "vitest"
import { render, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

beforeEach(() => {
  installShinyWindowStub()
})

// A completed single tool call now rests as a quiet Tier-1 row that morphs into
// the full card on expand; open it to assert on the leaf card / result body.
function expandToolRow() {
  const row = document.querySelector(".shiny-chat-tool-group__row")
  if (row) act(() => fireEvent.click(row))
}

describe("Tool component bridge rendering", () => {
  it("renders a tool request card from a structured tool_request block", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_request",
              version: 1,
              request_id: "req-1",
              tool_name: "get_weather",
              title: "Get Weather",
              arguments: '{"city":"NYC"}',
            },
          ],
        },
      })
    })

    // A running single call rests as a Tier-1 row (with a spinner) carrying the
    // tool title; the full card appears only on expand.
    expect(document.querySelector(".shiny-chat-tool-group__row")).toBeTruthy()
    expect(document.querySelector(".spinner-border")).toBeTruthy()
    expect(
      document.querySelector(".shiny-chat-tool-group__title")?.textContent,
    ).toContain("Get Weather")

    expandToolRow()
    expect(document.querySelector(".shiny-tool-card")).toBeTruthy()
  })

  it("renders a tool result card and hides the corresponding request", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    // First send a tool request
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_request",
              version: 1,
              request_id: "req-2",
              tool_name: "get_weather",
              arguments: "{}",
            },
          ],
        },
      })
    })

    // Then send the result
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-2",
              tool_name: "get_weather",
              status: "success",
              value: "Sunny, 72°F",
              value_type: "text",
            },
          ],
        },
      })
    })

    // The result rests as a row; expand it to reveal the leaf card body.
    expandToolRow()
    const resultDiv = document.querySelector(".shiny-tool-result__result")
    expect(resultDiv).toBeTruthy()
    expect(resultDiv?.textContent).toContain("Sunny, 72°F")
  })

  it("hides an existing tool request when a matching tool result arrives without an explicit hide action", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_request",
              version: 1,
              request_id: "req-inline-hide",
              tool_name: "get_weather",
              arguments: "{}",
            },
          ],
        },
      })
    })

    // A running request renders with a spinner glyph.
    expect(document.querySelector(".spinner-border")).toBeTruthy()

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-inline-hide",
              tool_name: "get_weather",
              status: "success",
              value: "Sunny, 72°F",
              value_type: "text",
            },
          ],
        },
      })
    })

    // The result supersedes the request: the running (spinner) glyph is gone,
    // and the result value is shown once the row is expanded.
    expect(document.querySelector(".spinner-border")).toBeNull()
    expandToolRow()
    expect(document.body.textContent).toContain("Sunny, 72°F")
  })

  it("hides an existing tool request when a matching streamed tool result arrives via block_insert", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_request",
              version: 1,
              request_id: "req-stream-hide",
              tool_name: "get_weather",
              arguments: "{}",
            },
          ],
        },
      })
    })

    expect(document.querySelector(".spinner-border")).toBeTruthy()

    // Stream the result as a structured block_insert
    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [],
        },
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "block_insert",
        block: {
          type: "tool_result",
          version: 1,
          request_id: "req-stream-hide",
          tool_name: "get_weather",
          status: "success",
          value: "Done",
          value_type: "text",
        },
      })
    })

    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(document.querySelector(".spinner-border")).toBeNull()
    expandToolRow()
    expect(document.body.textContent).toContain("Done")
  })

  // Supersession is derived from the result's own content, so a call whose
  // result never arrives — a cancelled stream, a dropped connection, a server
  // that errored after dispatching — keeps its request row. The former
  // `hide_tool_request` action was sent *before* the result and could never be
  // withdrawn, so this case lost the tool call permanently.
  it("keeps a request row when no result ever arrives", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_request",
              version: 1,
              request_id: "req-3",
              tool_name: "search",
              arguments: "{}",
            },
          ],
        },
      })
    })

    // The running request rests as a Tier-1 row.
    expect(document.querySelector(".shiny-chat-tool-group__row")).toBeTruthy()

    // The conversation moves on without a result for req-3 ever arriving.
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            { content: "Sorry, that was cut short.", content_type: "markdown" },
          ],
        },
      })
    })

    // The row is still there — the call is visibly stuck, not silently gone.
    expect(document.querySelector(".shiny-chat-tool-group__row")).toBeTruthy()
    expect(document.body.textContent).toContain("Sorry, that was cut short.")
  })

  it("hides a preloaded tool request when a matching preloaded tool result is rendered", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
        initialMessages={[
          {
            id: "msg-request",
            role: "assistant",
            content: "",
            streaming: false,
            blocks: [
              {
                type: "tool_loop",
                content: "",
                contentType: "html",
                grouping: "tool",
                groups: [
                  {
                    key: "tool:search",
                    toolName: "search",
                    title: undefined,
                    titleSettled: false,
                    icon: undefined,
                    count: 1,
                    segments: [
                      {
                        toolName: "search",
                        count: 1,
                        settled: false,
                      },
                    ],
                    calls: [
                      {
                        requestId: "req-preloaded",
                        localId: "req-preloaded",
                        toolName: "search",
                        status: "running",
                        structured: true,
                      },
                    ],
                  },
                ],
              },
            ],
          },
          {
            id: "msg-result",
            role: "assistant",
            content: "",
            streaming: false,
            blocks: [
              {
                type: "tool_loop",
                content: "",
                contentType: "html",
                grouping: "tool",
                groups: [
                  {
                    key: "tool:search",
                    toolName: "search",
                    title: undefined,
                    titleSettled: true,
                    icon: undefined,
                    count: 1,
                    segments: [
                      {
                        toolName: "search",
                        count: 1,
                        settled: true,
                      },
                    ],
                    calls: [
                      {
                        requestId: "req-preloaded",
                        localId: "req-preloaded",
                        toolName: "search",
                        status: "success",
                        value: "Done",
                        valueType: "text",
                        structured: true,
                      },
                    ],
                  },
                ],
              },
            ],
          },
        ]}
      />,
    )

    // The preloaded result supersedes the preloaded request (no spinner card).
    expect(document.querySelector(".spinner-border")).toBeNull()
    expandToolRow()
    expect(document.body.textContent).toContain("Done")
  })

  it("renders a user-specified icon on a successful tool result", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    const folderIcon = '<svg class="bi bi-folder2-open">folder</svg>'

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-icon",
              tool_name: "list_files",
              title: "List Files",
              status: "success",
              value: "file1.txt",
              value_type: "text",
              icon: folderIcon,
            },
          ],
        },
      })
    })

    // The tool's identity icon leads the resting Tier-1 row.
    const glyph = document.querySelector(".shiny-chat-tool-group__glyph")
    expect(glyph).toBeTruthy()
    expect(glyph!.innerHTML).toContain("bi-folder2-open")
  })

  it("falls back to a bare dot glyph when no icon is specified on a successful tool result", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-no-icon",
              tool_name: "get_weather",
              status: "success",
              value: "Sunny",
              value_type: "text",
            },
          ],
        },
      })
    })

    // Should lead with the muted identity dot (never a wrench).
    const glyph = document.querySelector(".shiny-chat-tool-group__glyph")
    expect(glyph).toBeTruthy()
    expect(glyph!.innerHTML).toContain("shiny-chat-tool-glyph-dot")
    expect(glyph!.innerHTML).not.toContain("bi-wrench-adjustable")
  })

  it("renders the empty-result placeholder when a tool result value is an empty string", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[
          "image/png",
          "image/jpeg",
          "image/gif",
          "image/webp",
          "application/pdf",
        ]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-empty",
              tool_name: "get_weather",
              status: "success",
              value: "",
              value_type: "text",
              show_request: true,
              full_screen: true,
              expanded: true,
            },
          ],
        },
      })
    })

    expect(document.querySelector(".shiny-tool-card")).toBeTruthy()
    expect(document.body.textContent).toContain("[Empty result]")
  })

  it("does not route tool markup in a preloaded user message", () => {
    // Preloaded/restored transcripts go through the same router; a user turn
    // that literally contains a tool tag must stay text, not become tool UI.
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()
    const typed =
      '<shiny-tool-result data-shinychat-react request-id="req-typed" tool-name="get_weather" status="success" value="Sunny" value-type="text"></shiny-tool-result>'

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[]}
        maxUploadSize={30000000}
        initialMessages={[
          {
            id: "msg-user",
            role: "user",
            content: typed,
            streaming: false,
            blocks: [
              { type: "content", content: typed, contentType: "markdown" },
            ],
          },
        ]}
      />,
    )

    expect(document.querySelector(".shiny-chat-tool-group__row")).toBeNull()
    expect(document.querySelector(".shiny-tool-card")).toBeNull()
  })

  it("splits thinking out of a preloaded message", () => {
    // Preloaded/restored transcripts get the same block construction as live
    // ones, so reasoning keeps its collapsible UI across a reload.
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()
    const content = "<thinking>Weighing options</thinking>Here you go."
    // ThinkingDisplay animates its label, which reads prefers-reduced-motion.
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockReturnValue({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }),
    )

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[]}
        maxUploadSize={30000000}
        initialMessages={[
          {
            id: "msg-thinking",
            role: "assistant",
            content,
            streaming: false,
            blocks: [{ type: "content", content, contentType: "markdown" }],
          },
        ]}
      />,
    )

    expect(document.querySelector(".shiny-chat-thinking")).toBeTruthy()
    expect(document.body.textContent).toContain("Here you go.")
    vi.unstubAllGlobals()
  })

  it("does not mount an HTML payload in tool_name when the card is expanded", () => {
    // tool_name is model-influenced (chatlas sets it from the tool-call
    // payload). When no server-attested title is provided, the fallback
    // `${toolName}()` is interpolated into the RawHTML title span, so the
    // name must be escaped — never mounted as a live element.
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        uploadAccept={[]}
        maxUploadSize={30000000}
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              type: "tool_result",
              version: 1,
              request_id: "req-xss",
              tool_name: "<img src=x onerror=alert(1)>",
              status: "success",
              value: "ok",
              value_type: "text",
              expanded: true,
            },
          ],
        },
      })
    })

    // The tool group row renders; expanded:true seeds the disclosure open so
    // the leaf card (whose header carries the title span — the RawHTML sink
    // under test) is already visible without clicking.
    expect(document.querySelector(".shiny-chat-tool-group__row")).toBeTruthy()
    expect(document.querySelector(".shiny-tool-card")).toBeTruthy()

    // The malicious tool_name must not mount as a live <img> element anywhere
    // in the document — it must render as escaped text in the title span.
    expect(document.querySelector('img[src="x"]')).toBeNull()
    expect(document.body.textContent).toContain("<img src=x onerror=alert(1)>")
  })
})
