import { describe, it, expect, vi } from "vitest"
import { render, screen, fireEvent } from "@testing-library/react"

vi.mock("../../src/chat/TiptapInput", async () => {
  const { FakeTiptapInput } = await import("../helpers/fakeTiptapInput")
  return { TiptapInput: FakeTiptapInput }
})

import { ChatMessages } from "../../src/chat/ChatMessages"
import type { ChatMessageData } from "../../src/chat/state"

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

describe("ChatMessages single-edit-at-a-time", () => {
  it("opening edit on one message closes any other open edit", () => {
    const messages = [
      userMessage({ id: "a", content: "first message" }),
      userMessage({ id: "b", content: "second message" }),
    ]
    render(
      <ChatMessages
        messages={messages}
        onEdit={() => {}}
        inputId="test-input"
      />,
    )

    const editButtons = screen.getAllByRole("button", {
      name: /edit message/i,
    })
    fireEvent.click(editButtons[0]!)
    expect(
      (
        screen.getByRole("textbox", {
          name: "Chat message",
        }) as HTMLTextAreaElement
      ).value,
    ).toBe("first message")

    fireEvent.click(editButtons[1]!)
    const editors = screen.getAllByRole("textbox", { name: "Chat message" })
    expect(editors).toHaveLength(1)
    expect((editors[0] as HTMLTextAreaElement).value).toBe("second message")
  })

  it("cancelling an edit clears the editing state", () => {
    const messages = [userMessage({ id: "a", content: "only message" })]
    render(
      <ChatMessages
        messages={messages}
        onEdit={() => {}}
        inputId="test-input"
      />,
    )

    fireEvent.click(screen.getByRole("button", { name: /edit message/i }))
    expect(screen.getByRole("textbox", { name: "Chat message" })).not.toBeNull()

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }))
    expect(screen.queryByRole("textbox", { name: "Chat message" })).toBeNull()
  })
})
