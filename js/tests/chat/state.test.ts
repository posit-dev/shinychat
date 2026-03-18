import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  chatReducer,
  initialState,
  allMessages,
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
    it("removes placeholder, sets streamingMessage, keeps input disabled", () => {
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
      expect(next.messages).toHaveLength(0)
      expect(next.streamingMessage).not.toBeNull()
      expect(next.streamingMessage!.streaming).toBe(true)
      expect(next.streamingMessage!.content).toBe("Hel")
      expect(next.inputDisabled).toBe(true)
    })
  })

  describe("chunk", () => {
    it("appends content when operation is 'append'", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "Hel" })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "lo",
        operation: "append",
      })
      expect(next.streamingMessage!.content).toBe("Hello")
      expect(next.messages).toBe(state.messages)
    })

    it("replaces content when operation is 'replace'", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "old" })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "new",
        operation: "replace",
      })
      expect(next.streamingMessage!.content).toBe("new")
      expect(next.messages).toBe(state.messages)
    })

    it("updates contentType when chunk provides one", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
        content_type: "html",
      })
      expect(next.streamingMessage!.contentType).toBe("html")
    })

    it("keeps contentType when chunk does not provide one", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next.streamingMessage!.contentType).toBe("markdown")
    })

    it("returns state unchanged when streamingMessage is null", () => {
      const state = makeState({ streamingMessage: null })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("returns state unchanged when streamingMessage is not assistant", () => {
      const userMsg: ChatMessageData = {
        id: "u",
        role: "user",
        content: "Hi",
        contentType: "semi-markdown",
        streaming: false,
      }
      const state = makeState({ streamingMessage: userMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("returns state unchanged when streamingMessage is not streaming", () => {
      const msg = makeAssistantMsg({ streaming: false })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })
  })

  describe("chunk_end", () => {
    it("moves streamingMessage to messages with streaming:false and re-enables input", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({ streamingMessage: msg, inputDisabled: true })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next.streamingMessage).toBeNull()
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.streaming).toBe(false)
      expect(next.inputDisabled).toBe(false)
    })

    it("returns state unchanged when streamingMessage is null", () => {
      const state = makeState({ streamingMessage: null })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next).toBe(state)
    })

    it("returns state unchanged when streamingMessage is not streaming", () => {
      const msg = makeAssistantMsg({ streaming: false })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next).toBe(state)
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

    it("resets inputDisabled when cleared during streaming", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        messages: [msg],
        inputDisabled: true,
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.inputDisabled).toBe(false)
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

  describe("chunk hiddenToolRequests handling", () => {
    it("does not derive hidden tool requests from rendered chunk HTML", () => {
      const msg = makeAssistantMsg({ streaming: true, content: "" })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content:
          '<shiny-tool-result request-id="req-from-html" tool-name="foo" status="success" value="ok" value-type="text"></shiny-tool-result>',
        operation: "replace",
      })
      expect(next.hiddenToolRequests).toBe(state.hiddenToolRequests)
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

  describe("removeLoadingMessage", () => {
    it("removes all placeholder messages, not just the last one", () => {
      const placeholder1: ChatMessageData = {
        id: "p1",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      const placeholder2: ChatMessageData = {
        id: "p2",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
      }
      const state = makeState({ messages: [placeholder1, placeholder2] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply",
          content_type: "markdown",
        },
      })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.isPlaceholder).toBeUndefined()
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

describe("allMessages", () => {
  it("returns messages when streamingMessage is null", () => {
    const msg = makeAssistantMsg()
    const state = makeState({ messages: [msg], streamingMessage: null })
    expect(allMessages(state)).toBe(state.messages)
  })

  it("appends streamingMessage to messages when present", () => {
    const committed = makeAssistantMsg({ id: "committed" })
    const streaming = makeAssistantMsg({ id: "streaming", streaming: true })
    const state = makeState({
      messages: [committed],
      streamingMessage: streaming,
    })
    const result = allMessages(state)
    expect(result).toHaveLength(2)
    expect(result[0]!.id).toBe("committed")
    expect(result[1]!.id).toBe("streaming")
  })
})
