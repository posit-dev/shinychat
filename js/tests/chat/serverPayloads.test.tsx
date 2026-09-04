import { describe, it, expect, beforeEach } from "vitest"
import { render, act } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

beforeEach(() => {
  installShinyWindowStub()
})

describe("server-shaped chat payloads", () => {
  it("preserves raw html semantics for assistant messages with content_type=html", () => {
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
              content:
                '<div class="server-html"><span>**not bold**</span><ul><li>literal asterisk item</li></ul></div><span class="server-tail">tail</span>',
              content_type: "html",
            },
          ],
        },
      })
    })

    const htmlBlock = document.querySelector(".server-html")
    expect(htmlBlock).toBeTruthy()
    expect(htmlBlock?.querySelector("strong")).toBeNull()
    expect(document.querySelector(".server-tail")?.textContent).toBe("tail")
    expect(htmlBlock?.textContent).toContain("**not bold**")
    expect(htmlBlock?.querySelectorAll("li")).toHaveLength(1)
  })

  it("keeps empty-string tool-result fields distinct from boolean attributes", () => {
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
              request_id: "req-empty-fields",
              tool_name: "get_weather",
              title: "Get Weather",
              status: "success",
              value: "",
              value_type: "text",
              request_call: "",
              footer: "",
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
    expect(document.body.textContent).not.toContain("Tool call")
    expect(document.querySelector(".card-footer")).toBeNull()
    expect(document.querySelector(".tool-fullscreen-toggle")).not.toBeNull()
    expect(
      document.querySelector(".card-header")?.getAttribute("aria-expanded"),
    ).toBe("true")
  })
})
