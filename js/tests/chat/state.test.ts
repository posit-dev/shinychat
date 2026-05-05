import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  chatReducer,
  initialState,
  type ChatState,
  type ChatMessageData,
} from "../../src/chat/state"
import { uuid } from "../../src/utils/uuid"

vi.mock("../../src/utils/uuid")

beforeEach(() => {
  let counter = 0
  vi.mocked(uuid).mockImplementation(() => `uuid-${++counter}`)
})

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...initialState, ...overrides }
}

function makeAssistantMsg(
  overrides: Partial<ChatMessageData> = {},
): ChatMessageData {
  const base: ChatMessageData = {
    id: "msg-1",
    role: "assistant",
    content: "Hello",
    contentType: "markdown",
    streaming: false,
    blocks: [],
    ...overrides,
  }
  if (base.blocks.length === 0) {
    base.blocks = [
      { type: "content", content: base.content, contentType: base.contentType },
    ]
  }
  return base
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
        contentType: "markdown",
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
        blocks: [],
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

    it("assigns uuid() when message has no id", () => {
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
        blocks: [],
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

    it("initializes blocks array from chunk_start content and type", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "Hel",
          content_type: "markdown",
        },
      })
      expect(next.streamingMessage!.blocks).toEqual([
        { type: "content", content: "Hel", contentType: "markdown" },
      ])
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
      const contentBlocks = next.streamingMessage!.blocks.filter(
        (b) => b.type === "content",
      )
      expect(contentBlocks).toHaveLength(1)
      expect(contentBlocks[0]).toEqual({
        type: "content",
        content: "new",
        contentType: "markdown",
      })
      expect(next.messages).toBe(state.messages)
    })

    it("starts a new block when content_type changes", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        content: "hello",
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "<div>widget</div>",
        operation: "append",
        content_type: "html",
      })
      const contentBlocks = next.streamingMessage!.blocks.filter(
        (b) => b.type === "content",
      )
      expect(contentBlocks).toHaveLength(2)
      expect(contentBlocks[0]).toEqual({
        type: "content",
        content: "hello",
        contentType: "markdown",
      })
      expect(contentBlocks[1]).toEqual({
        type: "content",
        content: "<div>widget</div>",
        contentType: "html",
      })
    })

    it("appends to current block when content_type matches", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        content: "hel",
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "lo",
        operation: "append",
      })
      const contentBlocks = next.streamingMessage!.blocks.filter(
        (b) => b.type === "content",
      )
      expect(contentBlocks).toHaveLength(1)
      expect(contentBlocks[0]).toEqual({
        type: "content",
        content: "hello",
        contentType: "markdown",
      })
    })

    it("top-level content is concat of all content blocks after type transition", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        content: "hello",
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "<div>widget</div>",
        operation: "append",
        content_type: "html",
      })
      expect(next.streamingMessage!.content).toBe("hello<div>widget</div>")
    })

    it("replace operation resets content blocks", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        content: "old",
        contentType: "html",
        blocks: [
          { type: "content", content: "frozen", contentType: "markdown" },
          { type: "content", content: "old", contentType: "html" },
        ],
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "new",
        operation: "replace",
      })
      const contentBlocks = next.streamingMessage!.blocks.filter(
        (b) => b.type === "content",
      )
      expect(contentBlocks).toHaveLength(1)
      expect(contentBlocks[0]).toEqual({
        type: "content",
        content: "new",
        contentType: "html",
      })
      expect(next.streamingMessage!.content).toBe("new")
    })

    it("updates contentType to match latest segment on type transition", () => {
      const msg = makeAssistantMsg({
        streaming: true,
        content: "hello",
        contentType: "markdown",
      })
      const state = makeState({ streamingMessage: msg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "<div>widget</div>",
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
        contentType: "markdown",
        streaming: false,
        blocks: [{ type: "content", content: "Hi", contentType: "markdown" }],
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
        blocks: [],
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
        blocks: [],
      }
      const placeholder2: ChatMessageData = {
        id: "p2",
        role: "assistant",
        content: "",
        contentType: "markdown",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
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

  describe("thinking blocks", () => {
    it("chunk_start with thinking content_type creates a thinking block", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "reasoning...",
          content_type: "thinking",
        },
      })
      expect(next.streamingMessage).not.toBeNull()
      expect(next.streamingMessage!.blocks).toHaveLength(1)
      expect(next.streamingMessage!.blocks[0]!.type).toBe("thinking")
      const block = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
        streaming: boolean
      }
      expect(block.content).toBe("reasoning...")
      expect(block.streaming).toBe(false)
    })

    it("thinking chunks append to existing thinking block", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          { type: "thinking", content: "part1", streaming: true, startedAt: 1 },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: " part2",
        content_type: "thinking",
        operation: "append",
      })
      const block = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
      }
      expect(block.content).toBe("part1 part2")
    })

    it("transition from thinking to markdown finalizes thinking block", () => {
      vi.spyOn(Date, "now").mockReturnValue(5000)
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          {
            type: "thinking",
            content: "thought",
            streaming: true,
            startedAt: 3000,
          },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "response",
        content_type: "markdown",
        operation: "append",
      })
      expect(next.streamingMessage!.blocks).toHaveLength(2)
      const thinkBlock = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        streaming: boolean
        durationMs: number
      }
      expect(thinkBlock.streaming).toBe(false)
      expect(thinkBlock.durationMs).toBe(2000)
      const contentBlock = next.streamingMessage!.blocks[1] as {
        type: "content"
        content: string
      }
      expect(contentBlock.content).toBe("response")
      vi.restoreAllMocks()
    })

    it("topic tags are extracted from thinking content", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          { type: "thinking", content: "", streaming: true, startedAt: 1 },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "before <topic>analyzing</topic> after",
        content_type: "thinking",
        operation: "append",
      })
      const block = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
        topic: string | null
      }
      expect(block.topic).toBe("analyzing")
      expect(block.content).toContain("shinychat-thinking-topic")
      expect(block.content).not.toContain("<topic>")
    })

    it("partial topic tag is buffered across chunks", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          { type: "thinking", content: "", streaming: true, startedAt: 1 },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })

      // First chunk ends with partial tag
      const next1 = chatReducer(state, {
        type: "chunk",
        content: "some text <top",
        content_type: "thinking",
        operation: "append",
      })
      const block1 = next1.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
        topicBuffer: string
      }
      expect(block1.topicBuffer).toBe("<top")
      expect(block1.content).toBe("some text ")

      // Second chunk completes the tag
      const next2 = chatReducer(next1, {
        type: "chunk",
        content: "ic>hello</topic> more",
        content_type: "thinking",
        operation: "append",
      })
      const block2 = next2.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
        topic: string | null
        topicBuffer: string
      }
      expect(block2.topic).toBe("hello")
      expect(block2.topicBuffer).toBe("")
      expect(block2.content).toContain("shinychat-thinking-topic")
    })

    it("topicBuffer is flushed on finalization (chunk_end)", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          {
            type: "thinking",
            content: "text ",
            topicBuffer: "<topi",
            streaming: true,
            startedAt: 1,
          },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, { type: "chunk_end" })
      const msg = next.messages[next.messages.length - 1]!
      const block = msg.blocks[0] as {
        type: "thinking"
        content: string
        topicBuffer: string
        streaming: boolean
      }
      expect(block.content).toBe("text <topi")
      expect(block.topicBuffer).toBe("")
      expect(block.streaming).toBe(false)
    })

    it("topicBuffer is flushed on transition to markdown", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          {
            type: "thinking",
            content: "thought ",
            topicBuffer: "<t",
            streaming: true,
            startedAt: 1,
          },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "response",
        content_type: "markdown",
        operation: "append",
      })
      const thinkBlock = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
        topicBuffer: string
      }
      expect(thinkBlock.content).toBe("thought <t")
      expect(thinkBlock.topicBuffer).toBe("")
    })

    it("multiple thinking→content cycles produce interleaved blocks", () => {
      const state = makeState()
      let s = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "",
          content_type: "thinking",
        },
      })
      s = chatReducer(s, {
        type: "chunk",
        content: "thought1",
        content_type: "thinking",
        operation: "append",
      })
      s = chatReducer(s, {
        type: "chunk",
        content: "response1",
        content_type: "markdown",
        operation: "append",
      })
      s = chatReducer(s, {
        type: "chunk",
        content: "thought2",
        content_type: "thinking",
        operation: "append",
      })
      s = chatReducer(s, {
        type: "chunk",
        content: "response2",
        content_type: "markdown",
        operation: "append",
      })
      s = chatReducer(s, { type: "chunk_end" })

      const msg = s.messages[s.messages.length - 1]!
      expect(msg.blocks).toHaveLength(4)
      expect(msg.blocks[0]!.type).toBe("thinking")
      expect(msg.blocks[1]!.type).toBe("content")
      expect(msg.blocks[2]!.type).toBe("thinking")
      expect(msg.blocks[3]!.type).toBe("content")
    })

    it("remove_loading finalizes in-flight thinking blocks", () => {
      vi.spyOn(Date, "now").mockReturnValue(10000)
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          {
            type: "thinking",
            content: "partial thought",
            streaming: true,
            startedAt: 8000,
            topicBuffer: "<to",
          },
        ],
      })
      const state = makeState({
        streamingMessage: streamingMsg,
        inputDisabled: true,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.streamingMessage).toBeNull()
      expect(next.inputDisabled).toBe(false)

      const msg = next.messages[next.messages.length - 1]!
      const block = msg.blocks[0] as {
        type: "thinking"
        content: string
        streaming: boolean
        durationMs: number
        topicBuffer: string
      }
      expect(block.streaming).toBe(false)
      expect(block.content).toBe("partial thought<to")
      expect(block.topicBuffer).toBe("")
      expect(block.durationMs).toBe(2000)
      vi.restoreAllMocks()
    })

    it("empty thinking chunk does not create duplicate blocks", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [
          { type: "thinking", content: "text", streaming: true, startedAt: 1 },
        ],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, {
        type: "chunk",
        content: "",
        content_type: "thinking",
        operation: "append",
      })
      expect(next.streamingMessage!.blocks).toHaveLength(1)
      const block = next.streamingMessage!.blocks[0] as {
        type: "thinking"
        content: string
      }
      expect(block.content).toBe("text")
    })

    it("thinking block with no startedAt has undefined durationMs", () => {
      const streamingMsg = makeAssistantMsg({
        streaming: true,
        content: "",
        blocks: [{ type: "thinking", content: "x", streaming: true }],
      })
      const state = makeState({ streamingMessage: streamingMsg })
      const next = chatReducer(state, { type: "chunk_end" })
      const msg = next.messages[next.messages.length - 1]!
      const block = msg.blocks[0] as {
        type: "thinking"
        durationMs: number | undefined
      }
      expect(block.durationMs).toBeUndefined()
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
