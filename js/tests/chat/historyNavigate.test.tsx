import { describe, expect, test, vi, beforeEach } from "vitest"
import { act, fireEvent, render, screen } from "@testing-library/react"
import { ChatApp } from "../../src/chat/ChatApp"
import { getCurrentConversationId } from "../../src/chat/currentConversation"
import { createMockTransport, createMockShinyLifecycle } from "../helpers/mocks"

vi.mock("../../src/utils/navigate", () => ({
  navigateTo: vi.fn(),
}))

import { navigateTo } from "../../src/utils/navigate"

describe("history_navigate handling", () => {
  beforeEach(() => {
    localStorage.clear()
    vi.mocked(navigateTo).mockClear()
  })

  test("updates the conversation pointer synchronously, then navigates", () => {
    const transport = createMockTransport()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="chat"
        inputId="chat_user_input"
      />,
    )

    transport.fire("chat", {
      type: "history_navigate",
      url: "http://x/?_state_id_=abc",
      active_id: "c42",
    })

    expect(getCurrentConversationId("chat")).toBe("c42")
    expect(navigateTo).toHaveBeenCalledWith("http://x/?_state_id_=abc")
  })

  test("active_id null clears the pointer (New chat)", () => {
    const transport = createMockTransport()
    localStorage.setItem("shinychat-current:chat", "old-conv")
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="chat"
        inputId="chat_user_input"
      />,
    )

    transport.fire("chat", {
      type: "history_navigate",
      url: "http://x/app/",
      active_id: null,
    })

    expect(getCurrentConversationId("chat")).toBeNull()
    expect(navigateTo).toHaveBeenCalledWith("http://x/app/")
  })

  test("conversation selection updates local pointer before server acknowledgement", () => {
    const transport = createMockTransport()
    render(
      <ChatApp
        transport={transport}
        shinyLifecycle={createMockShinyLifecycle()}
        elementId="chat"
        inputId="chat_user_input"
      />,
    )

    act(() => {
      transport.fire("chat", {
        type: "history_update",
        enabled: true,
        conversations: [
          {
            id: "c1",
            title: "First",
            created_at: "2026-01-01T00:00:00.000Z",
            updated_at: "2026-01-01T00:00:00.000Z",
          },
          {
            id: "c2",
            title: "Second",
            created_at: "2026-01-02T00:00:00.000Z",
            updated_at: "2026-01-02T00:00:00.000Z",
          },
        ],
        active_id: "c1",
      })
    })
    expect(getCurrentConversationId("chat")).toBe("c1")

    fireEvent.click(
      screen.getByRole("button", { name: /conversation history/i }),
    )
    fireEvent.click(screen.getByText("Second"))

    expect(getCurrentConversationId("chat")).toBe("c2")
    expect(transport.sendHistorySelect).toHaveBeenCalledWith("chat", "c2")
  })
})
