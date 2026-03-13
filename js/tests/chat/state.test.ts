import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  chatReducer,
  initialState,
  type ChatState,
  type ChatMessageData,
} from "../../src/chat/state"

// crypto.randomUUID is used by the reducer; stub it for deterministic IDs
beforeEach(() => {
  let counter = 0
  vi.spyOn(crypto, "randomUUID").mockImplementation(
    () =>
      `uuid-${++counter}` as `${string}-${string}-${string}-${string}-${string}`,
  )
})

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...initialState, ...overrides }
}

function makeAssistantMsg(
  overrides: Partial<ChatMessageData> = {},
): ChatMessageData {
  return {
    id: "msg-1",
    role: "assistant",
    content: "Hello",
    contentType: "markdown",
    streaming: false,
    ...overrides,
  }
}

describe("chatReducer", () => {
  describe("INPUT_SENT", () => {
    it("adds user message and loading placeholder, disables input", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "Hi",
        role: "user",
      })

      expect(next.messages).toHaveLength(2)
      expect(next.messages[0]).toMatchObject({
        role: "user",
        content: "Hi",
        contentType: "semi-markdown",
        streaming: false,
      })
      expect(next.messages[1]).toMatchObject({
        role: "assistant",
        content: "",
        isPlaceholder: true,
      })
      expect(next.inputDisabled).toBe(true)
    })
  })

  describe("message", () => {
    it("removes loading placeholder and appends message", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      const state = makeState({ messages: [placeholder], inputDisabled: true })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply",
          content_type: "markdown",
        },
      })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.content).toBe("Reply")
      expect(next.messages[0]!.isPlaceholder).toBeUndefined()
      expect(next.inputDisabled).toBe(false)
    })

    it("appends correctly when no placeholder exists", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Hello",
          content_type: "markdown",
        },
      })
      expect(next.messages).toHaveLength(1)
    })

    it("assigns crypto.randomUUID when message has no id", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Hi",
          content_type: "markdown",
        },
      })
      expect(next.messages[0]!.id).toBe("uuid-1")
    })

    it("uses provided id when present", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          id: "custom-id",
          role: "assistant",
          content: "Hi",
          content_type: "markdown",
        },
      })
      expect(next.messages[0]!.id).toBe("custom-id")
    })

    it("maps content_type to contentType", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "<b>Hi</b>",
          content_type: "html",
        },
      })
      expect(next.messages[0]!.contentType).toBe("html")
    })
  })

  describe("chunk_start", () => {
    it("removes placeholder, adds streaming message, keeps input disabled", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      const state = makeState({
        messages: [placeholder],
        inputDisabled: true,
      })
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "Hel",
          content_type: "markdown",
        },
      })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.streaming).toBe(true)
      expect(next.messages[0]!.content).toBe("Hel")
      expect(next.inputDisabled).toBe(true)
    })
  })

  describe("chunk", () => {
    it("appends content when operation is 'append'", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "Hel" })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "lo",
        operation: "append",
      })
      expect(next.messages[0]!.content).toBe("Hello")
    })

    it("replaces content when operation is 'replace'", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "old" })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "new",
        operation: "replace",
      })
      expect(next.messages[0]!.content).toBe("new")
    })

    it("updates contentType when chunk provides one", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        contentType: "markdown",
      })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
        content_type: "html",
      })
      expect(next.messages[0]!.contentType).toBe("html")
    })

    it("keeps contentType when chunk does not provide one", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        contentType: "markdown",
      })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next.messages[0]!.contentType).toBe("markdown")
    })

    it("returns state unchanged when no messages exist", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("returns state unchanged when last message is not assistant", () => {
      const userMsg: ChatMessageData = {
        id: "u",
        role: "user",
        content: "Hi",
        contentType: "semi-markdown",
        streaming: false,
      }
      const state = makeState({ messages: [userMsg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("returns state unchanged when last message is not streaming", () => {
      const msg = makeAssistantMsg({ streaming: false })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })
  })

  describe("chunk_end", () => {
    it("sets streaming to false and re-enables input", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({ messages: [msg], inputDisabled: true })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next.messages[0]!.streaming).toBe(false)
      expect(next.inputDisabled).toBe(false)
    })

    it("returns state unchanged when no messages exist", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next.messages).toHaveLength(0)
    })
  })

  describe("clear", () => {
    it("wipes messages array", () => {
      const msg = makeAssistantMsg()
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, { type: "clear" })
      expect(next.messages).toEqual([])
    })

    it("resets hiddenToolRequests", () => {
      const state = makeState({
        messages: [makeAssistantMsg()],
        hiddenToolRequests: new Set(["req-1", "req-2"]),
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.hiddenToolRequests.size).toBe(0)
    })
  })

  describe("update_input", () => {
    it("updates inputPlaceholder when provided", () => {
      const state = makeState({ inputPlaceholder: "old" })
      const next = chatReducer(state, {
        type: "update_input",
        placeholder: "new placeholder",
      })
      expect(next.inputPlaceholder).toBe("new placeholder")
    })

    it("leaves inputPlaceholder unchanged when placeholder is undefined", () => {
      const state = makeState({ inputPlaceholder: "keep" })
      const next = chatReducer(state, {
        type: "update_input",
      })
      expect(next.inputPlaceholder).toBe("keep")
    })
  })

  describe("remove_loading", () => {
    it("removes trailing placeholder and re-enables input", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      const state = makeState({
        messages: [placeholder],
        inputDisabled: true,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.messages).toHaveLength(0)
      expect(next.inputDisabled).toBe(false)
    })

    it("does not remove non-placeholder last message", () => {
      const msg = makeAssistantMsg()
      const state = makeState({ messages: [msg], inputDisabled: true })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.messages).toHaveLength(1)
      expect(next.inputDisabled).toBe(false)
    })
  })

  describe("chunk auto-hides tool requests when content has tool results", () => {
    it("hides request IDs found in replace-operation chunk content", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "" })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content:
          '<shiny-tool-result request-id="req-2" tool-name="foo" status="success" value="ok" value-type="text"></shiny-tool-result>',
        operation: "replace",
      })
      expect(next.hiddenToolRequests.has("req-2")).toBe(true)
    })

    it("does not scan append-operation chunks for tool results", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "" })
      const state = makeState({ messages: [msg] })
      const next = chatReducer(state, {
        type: "chunk",
        content:
          '<shiny-tool-result request-id="req-append" tool-name="foo" status="success" value="ok" value-type="text"></shiny-tool-result>',
        operation: "append",
      })
      expect(next.hiddenToolRequests.has("req-append")).toBe(false)
    })
  })

  describe("hide_tool_request", () => {
    it("adds requestId to hiddenToolRequests", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "hide_tool_request",
        requestId: "req-1",
      })
      expect(next.hiddenToolRequests.has("req-1")).toBe(true)
    })

    it("returns state unchanged for duplicate IDs (no re-render)", () => {
      const state = makeState({
        hiddenToolRequests: new Set(["req-1"]),
      })
      const next = chatReducer(state, {
        type: "hide_tool_request",
        requestId: "req-1",
      })
      expect(next).toBe(state)
    })
  })

  describe("unknown action", () => {
    it("returns state unchanged", () => {
      const state = makeState()
      const next = chatReducer(state, { type: "bogus" } as never)
      expect(next).toBe(state)
    })
  })
})
