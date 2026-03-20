import { describe, it, expect, vi, beforeEach } from "vitest"
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

function installScrollMetrics(
  element: HTMLElement,
  {
    scrollTop = 0,
    scrollHeight = 1000,
    clientHeight = 500,
  }: {
    scrollTop?: number
    scrollHeight?: number
    clientHeight?: number
  } = {},
) {
  let currentScrollTop = scrollTop

  Object.defineProperty(element, "scrollTop", {
    get: () => currentScrollTop,
    set: (value: number) => {
      currentScrollTop = value
    },
    configurable: true,
  })

  Object.defineProperty(element, "scrollHeight", {
    get: () => scrollHeight,
    configurable: true,
  })

  Object.defineProperty(element, "clientHeight", {
    get: () => clientHeight,
    configurable: true,
  })

  const scrollToMock = vi.fn(
    (arg1?: ScrollToOptions | number, _arg2?: number) => {
      if (typeof arg1 === "object" && typeof arg1?.top === "number") {
        currentScrollTop = arg1.top
      }
    },
  )
  element.scrollTo = scrollToMock as typeof element.scrollTo

  return element.scrollTo as ReturnType<typeof vi.fn>
}

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

  it("auto-scrolls for a non-streaming assistant reply when pinned to bottom", async () => {
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

    const messagesEl = document.querySelector(
      ".shiny-chat-messages",
    ) as HTMLElement | null
    expect(messagesEl).toBeTruthy()
    const scrollToSpy = installScrollMetrics(messagesEl!)

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

    expect(scrollToSpy).toHaveBeenCalledWith({
      top: 1000,
      behavior: "smooth",
    })
  })

  it("re-engages auto-scroll for a non-streaming assistant reply even after the user scrolls up", async () => {
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

    const messagesEl = document.querySelector(
      ".shiny-chat-messages",
    ) as HTMLElement | null
    expect(messagesEl).toBeTruthy()
    const scrollToSpy = installScrollMetrics(messagesEl!, { scrollTop: 500 })

    await act(async () => {
      Object.defineProperty(messagesEl!, "scrollTop", {
        get: () => 500,
        configurable: true,
      })
      messagesEl!.dispatchEvent(new Event("scroll"))
    })

    await act(async () => {
      Object.defineProperty(messagesEl!, "scrollTop", {
        get: () => 300,
        configurable: true,
      })
      messagesEl!.dispatchEvent(new Event("scroll"))
    })

    scrollToSpy.mockClear()

    await act(async () => {
      transport.fire("test-chat", {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply after scroll up",
          content_type: "markdown",
        },
      })
    })

    // Non-streaming messages re-engage stickToBottom (via engageStickToBottom
    // in ChatContainer), so scrollTo IS expected even after the user scrolled up.
    expect(scrollToSpy).toHaveBeenCalledWith({
      top: 1000,
      behavior: "smooth",
    })
  })
})
