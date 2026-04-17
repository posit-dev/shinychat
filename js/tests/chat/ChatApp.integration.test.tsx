import { describe, it, expect, beforeEach } from "vitest"
import { render, screen, act, fireEvent } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import {
  createMockTransport,
  createMockShinyLifecycle,
  installShinyWindowStub,
} from "../helpers/mocks"

beforeEach(() => {
  installShinyWindowStub()
})

describe("ChatApp integration: full message flow", () => {
  it("user message triggers transport.sendInput", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    const textarea = screen.getByPlaceholderText(
      "Type...",
    ) as HTMLTextAreaElement

    await act(async () => {
      fireEvent.change(textarea, { target: { value: "Hello from user" } })
      fireEvent.keyDown(textarea, { code: "Enter", key: "Enter" })
    })

    expect(transport.sendInput).toHaveBeenCalledWith(
      "test-input",
      "Hello from user",
    )
  })

  it("streaming chunks render assistant message", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: { role: "assistant", content: "", content_type: "markdown" },
      })
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "Hello world",
        operation: "append",
      })
    })

    await act(async () => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(screen.getByText("Hello world")).toBeTruthy()
  })

  it("streaming dot appears during streaming and disappears after chunk_end", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk_start",
        message: { role: "assistant", content: "", content_type: "markdown" },
      })
    })

    await act(async () => {
      transport.fire("test-chat", {
        type: "chunk",
        content: "Streaming...",
        operation: "append",
      })
    })

    expect(document.querySelector(".markdown-stream-dot")).not.toBeNull()

    await act(async () => {
      transport.fire("test-chat", { type: "chunk_end" })
    })

    expect(document.querySelector(".markdown-stream-dot")).toBeNull()
  })

  it("renders a non-streaming assistant reply", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Complete reply",
          content_type: "markdown",
        },
      })
    })

    expect(screen.getByText("Complete reply")).toBeTruthy()
  })

  it("scroll-to-bottom button is hidden when at bottom (default state)", async () => {
    const transport = createMockTransport()
    const shinyLifecycle = createMockShinyLifecycle()

    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={shinyLifecycle}
        elementId="test-chat"
        inputId="test-input"
        placeholder="Type..."
      />,
    )

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply",
          content_type: "markdown",
        },
      })
    })

    // When at bottom (default), the scroll-to-bottom button should not appear
    expect(document.querySelector(".shiny-chat-scroll-to-bottom")).toBeNull()
  })
})
