import { describe, it, expect, beforeEach } from "vitest"
import {
  getCurrentConversationId,
  setCurrentConversationId,
} from "../../src/chat/currentConversation"

beforeEach(() => {
  localStorage.clear()
})

describe("getCurrentConversationId", () => {
  it("returns null when nothing is stored for the element", () => {
    expect(getCurrentConversationId("my-chat")).toBeNull()
  })

  it("returns the stored conversation id", () => {
    localStorage.setItem("shinychat-current:my-chat", "conv-abc")
    expect(getCurrentConversationId("my-chat")).toBe("conv-abc")
  })

  it("is scoped per element id", () => {
    localStorage.setItem("shinychat-current:chat-a", "conv-1")
    expect(getCurrentConversationId("chat-b")).toBeNull()
  })
})

describe("setCurrentConversationId", () => {
  it("stores the conversation id", () => {
    setCurrentConversationId("my-chat", "conv-xyz")
    expect(localStorage.getItem("shinychat-current:my-chat")).toBe("conv-xyz")
  })

  it("removes the entry when id is null", () => {
    localStorage.setItem("shinychat-current:my-chat", "conv-xyz")
    setCurrentConversationId("my-chat", null)
    expect(localStorage.getItem("shinychat-current:my-chat")).toBeNull()
  })

  it("is scoped per element id", () => {
    setCurrentConversationId("chat-a", "conv-1")
    setCurrentConversationId("chat-b", "conv-2")
    expect(localStorage.getItem("shinychat-current:chat-a")).toBe("conv-1")
    expect(localStorage.getItem("shinychat-current:chat-b")).toBe("conv-2")
  })
})
