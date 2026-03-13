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

describe("Tool component bridge rendering", () => {
  it("renders a tool request card from server HTML", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="req-1" tool-name="get_weather" tool-title="Get Weather" arguments=\'{"city":"NYC"}\'></shiny-tool-request>',
          content_type: "markdown",
        },
      })
    })

    // The React ToolRequest renders a ToolCard with class shiny-tool-card
    expect(document.querySelector(".shiny-tool-card")).toBeTruthy()
    // The title should contain the tool title
    expect(document.querySelector(".tool-title")?.textContent).toContain(
      "Get Weather",
    )
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
      />,
    )

    // First send a tool request
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="req-2" tool-name="get_weather" arguments="{}"></shiny-tool-request>',
          content_type: "markdown",
        },
      })
    })

    // Server sends hide action (arrives before result HTML in real flow)
    act(() => {
      transport.fire("test-chat", {
        type: "hide_tool_request",
        requestId: "req-2",
      })
    })

    // Then send the result
    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-result request-id="req-2" tool-name="get_weather" status="success" value="Sunny, 72°F" value-type="text"></shiny-tool-result>',
          content_type: "markdown",
        },
      })
    })

    // The result card should be visible with the text value
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
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="req-inline-hide" tool-name="get_weather" arguments="{}"></shiny-tool-request>',
          content_type: "markdown",
        },
      })
    })

    expect(document.querySelector(".shiny-tool-request")).toBeTruthy()

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-result request-id="req-inline-hide" tool-name="get_weather" status="success" value="Sunny, 72°F" value-type="text"></shiny-tool-result>',
          content_type: "markdown",
        },
      })
    })

    expect(document.querySelector(".shiny-tool-request")).toBeNull()
    expect(document.querySelector(".shiny-tool-result")).toBeTruthy()
  })

  it("hides an existing tool request when a matching streamed tool result replaces chunk content", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="req-stream-hide" tool-name="get_weather" arguments="{}"></shiny-tool-request>',
          content_type: "markdown",
        },
      })
    })

    expect(document.querySelector(".shiny-tool-request")).toBeTruthy()

    act(() => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "",
          content_type: "markdown",
        },
      })
    })

    act(() => {
      transport.fire("test-chat", {
        type: "chunk",
        content:
          '<shiny-tool-result request-id="req-stream-hide" tool-name="get_weather" status="success" value="Done" value-type="text"></shiny-tool-result>',
        operation: "replace",
      })
    })

    act(() => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(document.querySelector(".shiny-tool-request")).toBeNull()
    expect(document.querySelector(".shiny-tool-result")).toBeTruthy()
  })

  it("hide_tool_request action hides a rendered tool request", () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
      />,
    )

    act(() => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="req-3" tool-name="search" arguments="{}"></shiny-tool-request>',
          content_type: "markdown",
        },
      })
    })

    // Tool request card should be visible
    expect(document.querySelector(".shiny-tool-card")).toBeTruthy()

    // Server sends hide action
    act(() => {
      transport.fire("test-chat", {
        type: "hide_tool_request",
        requestId: "req-3",
      })
    })

    // Card should be gone (ToolRequest returns null when hidden)
    expect(document.querySelector(".shiny-tool-card")).toBeNull()
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
        initialMessages={[
          {
            id: "msg-request",
            role: "assistant",
            content:
              '<shiny-tool-request request-id="req-preloaded" tool-name="search" arguments="{}"></shiny-tool-request>',
            contentType: "markdown",
            streaming: false,
          },
          {
            id: "msg-result",
            role: "assistant",
            content:
              '<shiny-tool-result request-id="req-preloaded" tool-name="search" status="success" value="Done" value-type="text"></shiny-tool-result>',
            contentType: "markdown",
            streaming: false,
          },
        ]}
      />,
    )

    expect(document.querySelector(".shiny-tool-request")).toBeNull()
    expect(document.querySelector(".shiny-tool-result")).toBeTruthy()
  })
})
