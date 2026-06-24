import { describe, expect, test, vi, beforeEach } from "vitest"
import { render } from "@testing-library/react"
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
})
