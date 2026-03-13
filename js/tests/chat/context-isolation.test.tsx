import { describe, it, expect, beforeEach } from "vitest"
import { render, act, screen } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

beforeEach(() => {
  installShinyWindowStub()
})

describe("ChatInputState / ChatToolState isolation", () => {
  it("hiding a tool request does not disturb the input textarea", async () => {
    const transport = createMockTransport()
    const shiny = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shiny}
        elementId="test"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement

    // Send a message containing a tool request
    await act(async () => {
      transport.fire("test", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="r1" tool-name="foo" arguments="{}"></shiny-tool-request>',
          content_type: "html",
        },
      })
    })

    // Simulate user typing
    textarea.value = "user is typing"

    // Hide the tool request
    await act(async () => {
      transport.fire("test", { type: "hide_tool_request", requestId: "r1" })
    })

    // Textarea value must not be disturbed
    expect(textarea.value).toBe("user is typing")
  })

  it("input state changes do not hide a visible tool request", async () => {
    const transport = createMockTransport()
    const shiny = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shiny}
        elementId="test"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    // Send a message containing a tool request
    await act(async () => {
      transport.fire("test", {
        type: "message",
        message: {
          role: "assistant",
          content:
            '<shiny-tool-request request-id="r2" tool-name="bar" arguments="{}"></shiny-tool-request>',
          content_type: "html",
        },
      })
    })

    expect(document.querySelector(".shiny-tool-request")).not.toBeNull()

    // Change input state
    await act(async () => {
      transport.fire("test", {
        type: "update_input",
        placeholder: "New placeholder...",
      })
    })

    // Tool request must still be visible
    expect(document.querySelector(".shiny-tool-request")).not.toBeNull()
  })
})
