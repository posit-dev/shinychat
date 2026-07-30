import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  chatReducer,
  contentFromBlocks,
  initialState,
  routeToolBlocks,
  type ChatState,
  type ChatMessageData,
  type GreetingData,
  type MessageBlock,
  type ToolLoopBlock,
  type ToolGrouping,
} from "../../src/chat/state"
import type { ContentType } from "../../src/transport/types"
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
    streaming: false,
    blocks: [],
    ...overrides,
  }
  if (base.blocks.length === 0) {
    base.blocks = [
      { type: "content", content: base.content, contentType: "markdown" },
    ]
  }
  return base
}

describe("chatReducer", () => {
  describe("INPUT_SENT", () => {
    it("INPUT_SENT stores attached image data URLs on the user message", () => {
      const next = chatReducer(initialState, {
        type: "INPUT_SENT",
        content: "look at this",
        role: "user",
        attachments: [
          {
            mime: "image/png",
            data_url: "data:image/png;base64,AAA",
            name: "",
            size: 0,
          },
          {
            mime: "image/jpeg",
            data_url: "data:image/jpeg;base64,BBB",
            name: "",
            size: 0,
          },
        ],
      })
      const userMsg = next.messages.find((m) => m.role === "user")
      expect(userMsg?.attachments?.map((a) => a.data_url)).toEqual([
        "data:image/png;base64,AAA",
        "data:image/jpeg;base64,BBB",
      ])
    })

    it("INPUT_SENT without images leaves attachments undefined", () => {
      const next = chatReducer(initialState, {
        type: "INPUT_SENT",
        content: "no images",
        role: "user",
      })
      const userMsg = next.messages.find((m) => m.role === "user")
      expect(userMsg?.attachments).toBeUndefined()
    })

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
        streaming: false,
      })
      expect(next.messages[1]).toMatchObject({
        role: "assistant",
        content: "",
        isPlaceholder: true,
      })
      expect(next.inputDisabled).toBe(true)
    })

    it("with awaitResponse=false adds only the user message and does not disable input", () => {
      const greeting: GreetingData = {
        content: "Hello!",
        contentType: "markdown",
        streaming: false,
        status: "visible",
        options: {},
        blocks: [
          { type: "content", content: "Hello!", contentType: "markdown" },
        ],
      }
      const state = makeState({ greeting })
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "/ping",
        role: "user",
        awaitResponse: false,
      })

      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]).toMatchObject({
        role: "user",
        content: "/ping",
      })
      expect(next.inputDisabled).toBe(false)
      expect(next.greeting?.status).toBe("dismissing")
    })
  })

  describe("update_cancel", () => {
    it("enables cancel when enable_cancel is true", () => {
      const state = makeState({ enableCancel: false })
      const next = chatReducer(state, {
        type: "update_cancel",
        enable_cancel: true,
      })
      expect(next.enableCancel).toBe(true)
    })

    it("disables cancel when enable_cancel is false", () => {
      const state = makeState({ enableCancel: true })
      const next = chatReducer(state, {
        type: "update_cancel",
        enable_cancel: false,
      })
      expect(next.enableCancel).toBe(false)
    })

    it("ignores the message when enableCancel was set explicitly (off)", () => {
      const state = makeState({
        enableCancel: false,
        enableCancelExplicit: true,
      })
      const next = chatReducer(state, {
        type: "update_cancel",
        enable_cancel: true,
      })
      // Explicit user choice wins over the client= auto-default
      expect(next.enableCancel).toBe(false)
      expect(next).toBe(state)
    })

    it("ignores the message when enableCancel was set explicitly (on)", () => {
      const state = makeState({
        enableCancel: true,
        enableCancelExplicit: true,
      })
      const next = chatReducer(state, {
        type: "update_cancel",
        enable_cancel: false,
      })
      expect(next.enableCancel).toBe(true)
    })
  })

  describe("update_upload", () => {
    it("enables upload when not explicit", () => {
      const state = makeState({ enableUpload: false })
      const next = chatReducer(state, {
        type: "update_upload",
        enable_upload: true,
      })
      expect(next.enableUpload).toBe(true)
    })

    it("is ignored when enableUploadExplicit is true", () => {
      const state = makeState({
        enableUpload: false,
        enableUploadExplicit: true,
      })
      const next = chatReducer(state, {
        type: "update_upload",
        enable_upload: true,
      })
      expect(next.enableUpload).toBe(false)
      expect(next).toBe(state)
    })

    it("preserves enableUpload + explicit flag across clear", () => {
      const state = makeState({
        enableUpload: true,
        enableUploadExplicit: true,
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.enableUpload).toBe(true)
      expect(next.enableUploadExplicit).toBe(true)
    })
  })

  describe("message", () => {
    it("removes loading placeholder and appends message", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
      }
      const state = makeState({ messages: [placeholder], inputDisabled: true })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Reply", content_type: "markdown" }],
        },
      })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.content).toBe("Reply")
      expect(next.messages[0]!.isPlaceholder).toBeUndefined()
      expect(next.inputDisabled).toBe(false)
    })

    it("maps payload attachments onto ChatMessageData.attachments", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "user",
          segments: [{ content: "look at this", content_type: "markdown" }],
          attachments: [
            {
              data_url: "data:image/png;base64,AAAA",
              name: "c.png",
              mime: "image/png",
              size: 3,
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.content).toBe("look at this")
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]).toEqual({
        type: "content",
        content: "look at this",
        contentType: "markdown",
      })
      expect(msg.attachments).toEqual([
        {
          mime: "image/png",
          data_url: "data:image/png;base64,AAAA",
          name: "c.png",
          size: 3,
        },
      ])
    })

    it("leaves attachments undefined when payload has no attachments field", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Hi", content_type: "markdown" }],
        },
      })
      expect(next.messages[0]!.attachments).toBeUndefined()
    })

    it("appends correctly when no placeholder exists", () => {
      const state = makeState({ messages: [] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Hello", content_type: "markdown" }],
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
          segments: [{ content: "Hi", content_type: "markdown" }],
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
          segments: [{ content: "Hi", content_type: "markdown" }],
        },
      })
      expect(next.messages[0]!.id).toBe("custom-id")
    })

    it("maps segment content_type to block contentType", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "<b>Hi</b>", content_type: "html" }],
        },
      })
      expect(next.messages[0]!.blocks[0]).toMatchObject({ contentType: "html" })
    })
  })

  describe("chunk_start", () => {
    it("removes placeholder, sets streamingMessage, keeps input disabled", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
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
          segments: [{ content: "Hel", content_type: "markdown" }],
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
          segments: [{ content: "Hel", content_type: "markdown" }],
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

    it("marks message as cancelled when cancelRequested is true", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: true,
      })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.cancelled).toBe(true)
      expect(next.cancelRequested).toBe(false)
    })

    it("does not mark message as cancelled when cancelRequested is false", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: false,
      })
      const next = chatReducer(state, { type: "chunk_end" })
      expect(next.messages).toHaveLength(1)
      expect(next.messages[0]!.cancelled).toBeUndefined()
      expect(next.cancelRequested).toBe(false)
    })
  })

  describe("CANCEL_REQUESTED", () => {
    it("sets cancelRequested to true", () => {
      const state = makeState({ cancelRequested: false })
      const next = chatReducer(state, { type: "CANCEL_REQUESTED" })
      expect(next.cancelRequested).toBe(true)
    })

    it("does not affect other state", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: false,
      })
      const next = chatReducer(state, { type: "CANCEL_REQUESTED" })
      expect(next.streamingMessage).toBe(msg)
      expect(next.inputDisabled).toBe(true)
    })
  })

  describe("update_slash_commands", () => {
    it("updates slashCommands to the provided list", () => {
      const state = makeState({ slashCommands: [] })
      const commands = [{ name: "help", description: "Show help", echo: true }]
      const next = chatReducer(state, {
        type: "update_slash_commands",
        commands,
      })
      expect(next.slashCommands).toEqual(commands)
    })

    it("replaces an existing slashCommands list", () => {
      const state = makeState({
        slashCommands: [{ name: "old", description: "Old", echo: true }],
      })
      const commands = [{ name: "new", description: "New", echo: true }]
      const next = chatReducer(state, {
        type: "update_slash_commands",
        commands,
      })
      expect(next.slashCommands).toEqual(commands)
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

    it("resets cancelRequested when cleared during cancel", () => {
      const state = makeState({ cancelRequested: true })
      const next = chatReducer(state, { type: "clear" })
      expect(next.cancelRequested).toBe(false)
    })

    it("preserves slashCommands across clear", () => {
      const commands = [{ name: "help", description: "Show help", echo: true }]
      const state = makeState({
        messages: [makeAssistantMsg()],
        slashCommands: commands,
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.messages).toEqual([])
      expect(next.slashCommands).toEqual(commands)
    })

    it("preserves history state across clear", () => {
      const conversations = [
        {
          id: "conv-1",
          title: "First chat",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
      ]
      let state = makeState({ messages: [makeAssistantMsg()] })
      state = chatReducer(state, {
        type: "history_update",
        enabled: true,
        conversations,
        active_id: "conv-1",
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.history).toEqual({
        enabled: true,
        conversations,
        activeId: "conv-1",
      })
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

    it("marks finalized streaming message as cancelled when cancelRequested is true", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: true,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      const finalized = next.messages[next.messages.length - 1]!
      expect(finalized.cancelled).toBe(true)
      expect(next.cancelRequested).toBe(false)
    })

    it("does not mark finalized streaming message as cancelled when cancelRequested is false", () => {
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: false,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      const finalized = next.messages[next.messages.length - 1]!
      expect(finalized.cancelled).toBeUndefined()
    })

    it("resets cancelRequested even without a streaming message", () => {
      const state = makeState({ cancelRequested: true })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.cancelRequested).toBe(false)
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
        streaming: false,
        isPlaceholder: true,
        blocks: [],
      }
      const placeholder2: ChatMessageData = {
        id: "p2",
        role: "assistant",
        content: "",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
      }
      const state = makeState({ messages: [placeholder1, placeholder2] })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Reply", content_type: "markdown" }],
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
          segments: [{ content: "reasoning...", content_type: "thinking" }],
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
      expect(block.streaming).toBe(true)
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
          segments: [{ content: "", content_type: "thinking" }],
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

  describe("segment-based message payloads", () => {
    it("builds blocks from multiple segments incl. thinking", () => {
      const next = chatReducer(initialState, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            { content: "reasoning", content_type: "thinking" },
            { content: "**answer**", content_type: "markdown" },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks.map((b) => b.type)).toEqual(["thinking", "content"])
      expect(msg.blocks[0]).toMatchObject({
        type: "thinking",
        content: "reasoning",
      })
      expect(msg.content).toBe("**answer**")
    })

    it("splits inline <thinking> tags inside a markdown segment (source B)", () => {
      const next = chatReducer(initialState, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content: "<thinking>\nhmm\n</thinking>\n\nhello",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks.map((b) => b.type)).toEqual(["thinking", "content"])
      expect(msg.blocks[1]).toMatchObject({ content: "hello" })
    })

    it("all-thinking segments produce empty content", () => {
      const next = chatReducer(initialState, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "reasoning", content_type: "thinking" }],
        },
      })
      const msg = next.messages[0]!
      expect(msg.content).toBe("")
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("thinking")
    })
  })

  describe("<thinking> tag detection", () => {
    it("splits <thinking> tags in non-streaming message into ThinkingBlock + ContentBlock", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "<thinking>\nI need to figure this out\n</thinking>\n\nHere is my answer.",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(2)
      expect(msg.blocks[0]!.type).toBe("thinking")
      expect((msg.blocks[0] as { content: string }).content).toBe(
        "I need to figure this out",
      )
      expect(msg.blocks[1]!.type).toBe("content")
      expect((msg.blocks[1] as { content: string }).content).toBe(
        "Here is my answer.",
      )
      expect(msg.content).toBe("Here is my answer.")
    })

    it("handles multiple <thinking> blocks interleaved with content", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "<thinking>\nFirst thought\n</thinking>\n\nSome text\n\n<thinking>\nSecond thought\n</thinking>\n\nMore text",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(4)
      expect(msg.blocks[0]!.type).toBe("thinking")
      expect(msg.blocks[1]!.type).toBe("content")
      expect(msg.blocks[2]!.type).toBe("thinking")
      expect(msg.blocks[3]!.type).toBe("content")
    })

    it("extracts <topic> tags within <thinking> blocks", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "<thinking>\n<topic>Planning</topic>\nLet me plan this\n</thinking>\n\nDone.",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      const thinkingBlock = msg.blocks[0] as { topic?: string | null }
      expect(thinkingBlock.topic).toBe("Planning")
    })

    it("detects <thinking> tags in streamed content at finalization", () => {
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
      state = chatReducer(state, {
        type: "chunk",
        content:
          "<thinking>\nHmm let me think\n</thinking>\n\nThe answer is 42.",
        operation: "append",
      })
      state = chatReducer(state, { type: "chunk_end" })

      const msg = state.messages[0]!
      expect(msg.blocks).toHaveLength(2)
      expect(msg.blocks[0]!.type).toBe("thinking")
      expect((msg.blocks[0] as { content: string }).content).toBe(
        "Hmm let me think",
      )
      expect(msg.blocks[1]!.type).toBe("content")
      expect((msg.blocks[1] as { content: string }).content).toBe(
        "The answer is 42.",
      )
    })

    it("leaves messages without <thinking> tags unchanged", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            { content: "Just a normal response", content_type: "markdown" },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
    })

    it("does not treat inline <thinking> in code blocks as thinking", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content: "Use `<thinking>` tags for reasoning.",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
    })

    it("does not treat <thinking> inside fenced code blocks as thinking", () => {
      const state = makeState()
      const content = [
        "Here's how to use thinking tags:",
        "",
        "```xml",
        "<thinking>",
        "This is reasoning content",
        "</thinking>",
        "```",
        "",
        "The model will reason before responding.",
      ].join("\n")
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content, content_type: "markdown" }],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
      expect(msg.blocks[0]!.content).toBe(content)
    })

    it("streams thinking in real-time when <thinking> tag arrives across chunks", () => {
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
      // First chunk: opening tag
      state = chatReducer(state, {
        type: "chunk",
        content: "<thinking>\n",
        operation: "append",
      })
      expect(state.streamingMessage!.insideThinkingTag).toBe(true)
      expect(state.streamingMessage!.blocks).toHaveLength(0)

      // Second chunk: thinking content
      state = chatReducer(state, {
        type: "chunk",
        content: "Let me reason about this...",
        operation: "append",
      })
      expect(state.streamingMessage!.blocks).toHaveLength(1)
      expect(state.streamingMessage!.blocks[0]!.type).toBe("thinking")
      expect(
        (state.streamingMessage!.blocks[0] as { streaming: boolean }).streaming,
      ).toBe(true)
      expect(
        (state.streamingMessage!.blocks[0] as { content: string }).content,
      ).toBe("Let me reason about this...")

      // Third chunk: closing tag + content start
      state = chatReducer(state, {
        type: "chunk",
        content: "\n</thinking>\n\nHere is the answer.",
        operation: "append",
      })
      expect(state.streamingMessage!.insideThinkingTag).toBe(false)
      expect(state.streamingMessage!.blocks).toHaveLength(2)
      expect(state.streamingMessage!.blocks[0]!.type).toBe("thinking")
      expect(
        (state.streamingMessage!.blocks[0] as { streaming: boolean }).streaming,
      ).toBe(false)
      expect(state.streamingMessage!.blocks[1]!.type).toBe("content")
      expect(
        (state.streamingMessage!.blocks[1] as { content: string }).content,
      ).toBe("Here is the answer.")
    })

    it("does not treat <thinking> as thinking when chunk boundary falls before it (not after newline)", () => {
      // The bug: a chunk ending with a backtick (or any non-newline) followed by a chunk
      // starting with <thinking> — the second chunk has empty `before`, which previously
      // caused the state machine to enter thinking mode incorrectly.
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
      // Chunk ends just before <thinking> with a backtick — not a newline boundary
      state = chatReducer(state, {
        type: "chunk",
        content: "replaces any `",
        operation: "append",
      })
      // Next chunk starts with <thinking> — must NOT enter thinking mode
      state = chatReducer(state, {
        type: "chunk",
        content: "<thinking>` content blocks",
        operation: "append",
      })
      state = chatReducer(state, { type: "chunk_end" })
      const msg = state.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
      expect((msg.blocks[0] as { content: string }).content).toContain(
        "<thinking>",
      )
    })

    it("recognizes <thinking> when chunk boundary falls on a real newline boundary", () => {
      // <thinking> arriving at the start of a new chunk IS valid if the previous chunk
      // ended with a newline (e.g. in an agentic loop between turns).
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
      state = chatReducer(state, {
        type: "chunk",
        content: "tool result\n",
        operation: "append",
      })
      state = chatReducer(state, {
        type: "chunk",
        content: "<thinking>\nreasoning\n</thinking>\n\nFinal answer.",
        operation: "append",
      })
      state = chatReducer(state, { type: "chunk_end" })
      const msg = state.messages[0]!
      expect(msg.blocks).toHaveLength(3)
      expect(msg.blocks[0]!.type).toBe("content")
      expect(msg.blocks[1]!.type).toBe("thinking")
      expect((msg.blocks[1] as { content: string }).content).toBe("reasoning")
      expect(msg.blocks[2]!.type).toBe("content")
    })

    it("does not treat inline <thinking>...</thinking> in backtick code span as thinking (non-streaming)", () => {
      // When both tags appear inside a backtick span the non-streaming path must exclude them
      const state = makeState()
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [
            {
              content:
                "The model wraps reasoning in `<thinking>I reason here</thinking>` tags.",
              content_type: "markdown",
            },
          ],
        },
      })
      const msg = next.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
    })

    it("does not treat <thinking> inside a fenced code block as thinking (streaming)", () => {
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })
      const chunks = [
        "Here's an example:\n",
        "```xml\n",
        "<thinking>\n",
        "This is code, not reasoning\n",
        "</thinking>\n",
        "```\n",
        "The model will reason before responding.",
      ]
      for (const chunk of chunks) {
        state = chatReducer(state, {
          type: "chunk",
          content: chunk,
          operation: "append",
        })
      }
      state = chatReducer(state, { type: "chunk_end" })
      const msg = state.messages[0]!
      expect(msg.blocks).toHaveLength(1)
      expect(msg.blocks[0]!.type).toBe("content")
    })

    it("streams thinking across many small chunks (simulating token-by-token)", () => {
      let state = makeState()
      state = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "", content_type: "markdown" }],
        },
      })

      const chunks = [
        "<thinking>\n",
        "First ",
        "part of ",
        "thinking.\n",
        "\n</thinking>\n\n",
        "The ",
        "response.",
      ]

      for (const chunk of chunks) {
        state = chatReducer(state, {
          type: "chunk",
          content: chunk,
          operation: "append",
        })
      }

      state = chatReducer(state, { type: "chunk_end" })
      const msg = state.messages[0]!
      expect(msg.blocks).toHaveLength(2)
      expect(msg.blocks[0]!.type).toBe("thinking")
      expect((msg.blocks[0] as { content: string }).content).toBe(
        "First part of thinking.\n",
      )
      expect(msg.blocks[1]!.type).toBe("content")
      expect((msg.blocks[1] as { content: string }).content).toBe(
        "The response.",
      )
    })
  })

  describe("history_update", () => {
    it("sets enabled, conversations, and activeId", () => {
      const conversations = [
        {
          id: "c1",
          title: "First",
          created_at: "2024-01-01T00:00:00Z",
          updated_at: "2024-01-01T00:00:00Z",
        },
        {
          id: "c2",
          title: "Second",
          created_at: "2024-01-02T00:00:00Z",
          updated_at: "2024-01-02T00:00:00Z",
        },
      ]
      const next = chatReducer(initialState, {
        type: "history_update",
        enabled: true,
        conversations,
        active_id: "c1",
      })
      expect(next.history).toEqual({
        enabled: true,
        conversations,
        activeId: "c1",
      })
    })

    it("replaces previous history state entirely", () => {
      const state = makeState({
        history: {
          enabled: true,
          conversations: [
            {
              id: "old",
              title: "Old",
              created_at: "2024-01-01T00:00:00Z",
              updated_at: "2024-01-01T00:00:00Z",
            },
          ],
          activeId: "old",
        },
      })
      const next = chatReducer(state, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      expect(next.history).toEqual({
        enabled: true,
        conversations: [],
        activeId: null,
      })
    })

    it("does not affect other state fields", () => {
      const state = makeState({ inputDisabled: true })
      const next = chatReducer(state, {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      expect(next.inputDisabled).toBe(true)
      expect(next.messages).toBe(state.messages)
    })
  })

  it("history_navigate is a state no-op (handled imperatively in ChatApp)", () => {
    const state = chatReducer(initialState, {
      type: "history_update",
      enabled: true,
      conversations: [],
      active_id: "c1",
    })
    const next = chatReducer(state, {
      type: "history_navigate",
      url: "http://x/?_state_id_=abc",
      active_id: "c1",
    })
    expect(next).toBe(state)
  })
})

describe("INPUT_SENT attachments", () => {
  it("stores attachments on the user message", () => {
    const next = chatReducer(initialState, {
      type: "INPUT_SENT",
      content: "hi",
      role: "user",
      attachments: [
        {
          mime: "application/pdf",
          data_url: "data:application/pdf;base64,AAA",
          name: "report.pdf",
          size: 0,
        },
      ],
    })
    const userMsg = next.messages.find((m) => m.role === "user")!
    expect(userMsg.attachments).toHaveLength(1)
    expect(userMsg.attachments![0]!.mime).toBe("application/pdf")
  })

  it("omits attachments when none are provided", () => {
    const next = chatReducer(initialState, {
      type: "INPUT_SENT",
      content: "hi",
      role: "user",
    })
    const userMsg = next.messages.find((m) => m.role === "user")!
    expect(userMsg.attachments).toBeUndefined()
  })
})

describe("routeToolBlocks (tool content router)", () => {
  function req(id: string, name: string, extra = ""): string {
    return `<shiny-tool-request data-shinychat-react request-id="${id}" tool-name="${name}" ${extra}></shiny-tool-request>`
  }
  function res(id: string, name: string, extra = ""): string {
    return `<shiny-tool-result data-shinychat-react request-id="${id}" tool-name="${name}" status="success" ${extra}></shiny-tool-result>`
  }
  function route(
    content: string,
    grouping: ToolGrouping = "tool",
  ): MessageBlock[] {
    return routeToolBlocks(
      [{ type: "content", content, contentType: "markdown" }],
      grouping,
      "assistant",
    )
  }
  function routeStreaming(
    content: string,
    grouping: ToolGrouping = "tool",
  ): MessageBlock[] {
    return routeToolBlocks(
      [{ type: "content", content, contentType: "markdown" }],
      grouping,
      "assistant",
      true,
    )
  }
  function loops(blocks: MessageBlock[]): ToolLoopBlock[] {
    return blocks.filter((b): b is ToolLoopBlock => b.type === "tool_loop")
  }

  it("leaves non-tool content untouched (fast path)", () => {
    const input: MessageBlock[] = [
      { type: "content", content: "just prose", contentType: "markdown" },
    ]
    const out = routeToolBlocks(input, "tool", "assistant")
    expect(out).toEqual(input)
  })

  it("passes thinking blocks through unchanged and as loop boundaries", () => {
    const input: MessageBlock[] = [
      { type: "content", content: res("1", "a"), contentType: "markdown" },
      { type: "thinking", content: "hmm", streaming: false },
      { type: "content", content: res("2", "a"), contentType: "markdown" },
    ]
    const out = routeToolBlocks(input, "tool", "assistant")
    expect(out.map((b) => b.type)).toEqual([
      "tool_loop",
      "thinking",
      "tool_loop",
    ])
  })

  const anonRes =
    '<shiny-tool-result data-shinychat-react tool-name="a" status="success"></shiny-tool-result>'

  it("keeps synthetic localIds distinct when adjacent loops from separate blocks merge", () => {
    // Anonymous calls in different source blocks used to both become
    // `__anon-0`; once merged, "none" grouping collapsed them into one group.
    const out = routeToolBlocks(
      [
        { type: "content", content: anonRes, contentType: "markdown" },
        { type: "content", content: anonRes, contentType: "markdown" },
      ],
      "none",
      "assistant",
    )
    const l = loops(out)
    expect(l).toHaveLength(1)
    expect(l[0]!.groups).toHaveLength(2)
    const ids = l[0]!.groups.flatMap((g) => g.calls).map((c) => c.localId)
    expect(new Set(ids).size).toBe(2)
  })

  it("leaves tool tags inside a code fence or inline code as literal prose", () => {
    const fenced =
      "Here is the protocol:\n\n```html\n" + res("1", "a") + "\n```\n"
    expect(loops(route(fenced))).toHaveLength(0)
    expect(route(fenced)).toEqual([
      { type: "content", content: fenced, contentType: "markdown" },
    ])

    const inline = "Use `" + res("1", "a") + "` to render a result."
    expect(loops(route(inline))).toHaveLength(0)
  })

  it("leaves tool tags inside a multi-backtick code span as literal prose", () => {
    // A span quoting a sample that itself contains a backtick needs ``…``.
    const doubled = "Write ``" + res("1", "a") + "`` verbatim."
    expect(loops(route(doubled))).toHaveLength(0)
  })

  it("does not let stray single backticks on separate lines swallow an element", () => {
    // Unbalanced backticks are common in prose; a code span must not pair
    // across lines, or it would suppress a real tool element between them.
    const strays = "don`t\n" + res("1", "a") + "\nit`s fine"
    const l = loops(route(strays))
    expect(l).toHaveLength(1)
    expect(l[0]!.groups[0]!.calls[0]!.requestId).toBe("1")
  })

  it("leaves tool tags inside a fence indented up to 3 spaces as literal prose", () => {
    // CommonMark allows 3 leading spaces on either fence, which is how an
    // example nested in a list item or blockquote is written.
    for (const pad of [" ", "  ", "   "]) {
      const fenced = `- Example:\n\n${pad}\`\`\`html\n${pad}${res("1", "a")}\n${pad}\`\`\`\n`
      expect(loops(route(fenced))).toHaveLength(0)
    }
  })

  it("treats a fence indented 4+ spaces as an indented code block, not a fence", () => {
    // Four spaces is an indented code block per CommonMark, and detecting one
    // needs block context this raw-string pass lacks — so no range is produced
    // and the sample still routes. Documented here so the behavior is a choice.
    const fenced = "    ```html\n    " + res("1", "a") + "\n    ```\n"
    expect(loops(route(fenced))).toHaveLength(1)
  })

  it("closes a fence with a longer run of backticks", () => {
    // The closer only has to be at least as long as the opener.
    const fenced = "```html\n" + res("1", "a") + "\n````\n"
    expect(loops(route(fenced))).toHaveLength(0)
  })

  it("leaves tool tags inside a tilde fence as literal prose", () => {
    const fenced = "~~~html\n" + res("1", "a") + "\n~~~\n"
    expect(loops(route(fenced))).toHaveLength(0)
  })

  it("still routes a real tool element alongside a fenced example", () => {
    const mixed = "```html\n" + res("1", "a") + "\n```\n\n" + res("2", "a")
    const l = loops(route(mixed))
    expect(l).toHaveLength(1)
    expect(l[0]!.groups[0]!.calls.map((c) => c.requestId)).toEqual(["2"])
  })

  it("leaves a tool tag under a not-yet-closed fence as prose while streaming", () => {
    // Mid-stream the opening fence has arrived but its closer has not, so the
    // sample would otherwise flash into live tool UI for a few chunks.
    const partial = "Example:\n\n```html\n" + res("1", "a") + "\n"
    expect(loops(routeStreaming(partial))).toHaveLength(0)
  })

  it("keeps the example as prose once its fence closes", () => {
    const complete = "Example:\n\n```html\n" + res("1", "a") + "\n```\n"
    expect(loops(routeStreaming(complete))).toHaveLength(0)
  })

  it("still routes a real element outside any fence while streaming", () => {
    // The to-EOF rule must only shield text after an *unmatched* opener.
    const mixed = "```html\n" + res("1", "a") + "\n```\n\n" + res("2", "a")
    const l = loops(routeStreaming(mixed))
    expect(l).toHaveLength(1)
    expect(l[0]!.groups[0]!.calls.map((c) => c.requestId)).toEqual(["2"])
  })

  it("routes a tool tag under an unclosed fence when the content never streamed", () => {
    // Without the shield flag the to-EOF rule is off, so an unclosed fence in
    // content that never came off a stream does not hide what follows it. This
    // is the un-shielded default; `finalizeMessage` opts in only when the
    // message it finalizes still has `insideFence` set.
    const partial = "Example:\n\n```html\n" + res("1", "a") + "\n"
    expect(loops(route(partial))).toHaveLength(1)
  })

  it("does not let a stray fence suppress a later real element when final", () => {
    // Preloaded/restored transcripts arrive as one markdown block and never
    // touch the streaming tag state machine, so they finalize (and route)
    // unshielded: one unbalanced ``` in prose must not hide the real tool
    // calls after it.
    const mixed = "Prose with a stray ```\n\nmore prose\n\n" + res("1", "a")
    const l = loops(route(mixed))
    expect(l).toHaveLength(1)
    expect(l[0]!.groups[0]!.calls.map((c) => c.requestId)).toEqual(["1"])
  })

  it("keeps a fenced example as prose when the stream ends mid-fence", () => {
    // A cancelled/truncated stream finalizes with `insideFence` still set, so
    // the shield stays on and the documented example must not pop into live
    // tool UI at the moment of finalization.
    const partial = "Example:\n\n```html\n" + res("1", "a") + "\n"
    const msg = makeAssistantMsg({
      streaming: true,
      content: partial,
      blocks: [{ type: "content", content: partial, contentType: "markdown" }],
      insideFence: true,
      fenceMarker: "```",
    })
    const next = chatReducer(makeState({ streamingMessage: msg }), {
      type: "remove_loading",
    })
    const finalized = next.messages[next.messages.length - 1]!
    expect(loops(finalized.blocks)).toHaveLength(0)
  })

  it("routes normally when the stream ends with no fence open", () => {
    // Same finalize path, flag clear: the element is real and must render.
    const content = "Result:\n\n" + res("1", "a")
    const msg = makeAssistantMsg({
      streaming: true,
      content,
      blocks: [{ type: "content", content, contentType: "markdown" }],
    })
    const next = chatReducer(makeState({ streamingMessage: msg }), {
      type: "remove_loading",
    })
    const finalized = next.messages[next.messages.length - 1]!
    expect(loops(finalized.blocks)).toHaveLength(1)
  })

  it("gives each call a loop-local unique localId, synthesizing one when request-id is absent", () => {
    // `localId` is what React keys and card DOM ids hang off, so it must stay
    // distinct even when the server omits `request-id`.
    const anon =
      '<shiny-tool-result data-shinychat-react tool-name="a" status="success"></shiny-tool-result>'
    const l = loops(route(anon + anon + res("1", "a"), "none"))
    const ids = l
      .flatMap((b) => b.groups.flatMap((g) => g.calls))
      .map((c) => c.localId)
    expect(ids).toHaveLength(3)
    expect(new Set(ids).size).toBe(3)
    expect(ids).toContain("1")
  })

  it("emits a single-call loop that morphs straight to a leaf", () => {
    const blocks = route(res("1", "get_weather", 'tool-title="Got weather"'))
    const l = loops(blocks)
    expect(l).toHaveLength(1)
    expect(l[0]!.groups).toHaveLength(1)
    expect(l[0]!.groups[0]!.count).toBe(1)
    expect(l[0]!.groups[0]!.calls[0]!.status).toBe("success")
  })

  it("pairs a request and result with the same id into one call", () => {
    const blocks = route(req("1", "search") + res("1", "search"))
    const l = loops(blocks)
    expect(l).toHaveLength(1)
    const calls = l[0]!.groups.flatMap((g) => g.calls)
    expect(calls).toHaveLength(1)
    expect(calls[0]!.status).toBe("success")
  })

  it("groups by tool name (default), order-independent, at first position", () => {
    const content = [
      res("1", "X"),
      res("2", "Y"),
      res("3", "Z"),
      res("4", "X"),
      res("5", "Y"),
    ].join("")
    const groups = loops(route(content, "tool"))[0]!.groups
    expect(groups.map((g) => g.toolName)).toEqual(["X", "Y", "Z"])
    expect(groups.map((g) => g.count)).toEqual([2, 2, 1])
  })

  it("grouping=none yields one group per call in order", () => {
    const content = [res("1", "X"), res("2", "Y"), res("3", "X")].join("")
    const groups = loops(route(content, "none"))[0]!.groups
    expect(groups).toHaveLength(3)
    expect(groups.every((g) => g.count === 1)).toBe(true)
  })

  it("grouping=all collapses the whole loop into one group", () => {
    const content = [res("1", "X"), res("2", "Y"), res("3", "Z")].join("")
    const groups = loops(route(content, "all"))[0]!.groups
    expect(groups).toHaveLength(1)
    expect(groups[0]!.count).toBe(3)
  })

  it("per-tool grouping override wins over the chat-level value", () => {
    const content = [
      res("1", "X", 'grouping="none"'),
      res("2", "Y"),
      res("3", "X", 'grouping="none"'),
      res("4", "Y"),
    ].join("")
    const groups = loops(route(content, "tool"))[0]!.groups
    // X is forced to none (two standalone groups); Y stays grouped (count 2)
    const xGroups = groups.filter((g) => g.toolName === "X")
    const yGroups = groups.filter((g) => g.toolName === "Y")
    expect(xGroups).toHaveLength(2)
    expect(yGroups).toHaveLength(1)
    expect(yGroups[0]!.count).toBe(2)
  })

  it("shows the definition (static) title while a single call is running", () => {
    const groups = loops(
      route(req("1", "search", 'tool-title="Searching"')),
    )[0]!.groups
    expect(groups[0]!.title).toBe("Searching")
    expect(groups[0]!.calls[0]!.status).toBe("running")
  })

  it("a single call shows its dynamic (result) title once a result arrives", () => {
    const content =
      req("1", "search", 'tool-title="Searching"') +
      res("1", "search", 'tool-title="Searched"')
    const groups = loops(route(content))[0]!.groups
    expect(groups[0]!.title).toBe("Searched")
    // The static (definition) title is retained separately on the call.
    expect(groups[0]!.calls[0]!.definitionTitle).toBe("Searching")
  })

  it("an aggregated group keeps the static header; calls carry their dynamic titles", () => {
    const content =
      req("1", "weather", 'tool-title="Weather Forecast"') +
      res("1", "weather", 'tool-title="Weather Forecast for Portland"') +
      req("2", "weather", 'tool-title="Weather Forecast"') +
      res("2", "weather", 'tool-title="Weather Forecast for San Francisco"')
    const groups = loops(route(content, "tool"))[0]!.groups
    expect(groups[0]!.count).toBe(2)
    // Header is the static definition title, not the first result's title.
    expect(groups[0]!.title).toBe("Weather Forecast")
    expect(groups[0]!.calls.map((c) => c.title)).toEqual([
      "Weather Forecast for Portland",
      "Weather Forecast for San Francisco",
    ])
  })

  it("aggregated group falls back to a result title when no request/definition title exists", () => {
    const content =
      res("1", "search", 'tool-title="Found A"') +
      res("2", "search", 'tool-title="Found B"')
    const groups = loops(route(content, "tool"))[0]!.groups
    expect(groups[0]!.title).toBe("Found A")
    expect(groups[0]!.count).toBe(2)
  })

  it("gives a homogeneous group exactly one segment carrying its own identity", () => {
    const content =
      req("1", "search", 'tool-title="Searching"') +
      res("1", "search", 'tool-title="Searched A"') +
      req("2", "search", 'tool-title="Searching"') +
      res("2", "search", 'tool-title="Searched B"')
    const g = loops(route(content, "tool"))[0]!.groups[0]!
    expect(g.segments).toEqual([
      { toolName: "search", title: "Searching", count: 2, settled: true },
    ])
    expect(g.title).toBe("Searching")
  })

  it("splits a loop-wide group into one segment per tool, in first-appearance order", () => {
    const content =
      req("1", "search", 'tool-title="Searching"') +
      res("1", "search", 'tool-title="Searched A"') +
      req("2", "search", 'tool-title="Searching"') +
      res("2", "search", 'tool-title="Searched B"') +
      res("3", "read_page", 'tool-title="Read page"')
    const g = loops(route(content, "all"))[0]!.groups[0]!
    // Each segment resolves its title by the same rule the group uses, scoped
    // to that tool: the aggregated `search` keeps its definition title, while
    // the lone `read_page` call shows its own result title.
    expect(g.segments).toEqual([
      { toolName: "search", title: "Searching", count: 2, settled: true },
      { toolName: "read_page", title: "Read page", count: 1, settled: true },
    ])
    // The group-level identity fields are unchanged (the first tool's).
    expect(g.toolName).toBe("search")
    expect(g.count).toBe(3)
  })

  it("settles each segment on its own tool's first result", () => {
    const content =
      res("1", "search", 'tool-title="Searched"') +
      req("2", "read_page", 'tool-title="Reading page"')
    const g = loops(route(content, "all"))[0]!.groups[0]!
    expect(g.segments.map((s) => [s.toolName, s.settled])).toEqual([
      ["search", true],
      ["read_page", false],
    ])
  })

  it("two tools annotated grouping=all share one heterogeneous bucket", () => {
    // Reachable at default chat settings: the mode is resolved per tool but the
    // bucket key is the literal string "all", so both tools land together.
    const content =
      res("1", "search", 'grouping="all"') +
      res("2", "read_page", 'grouping="all"')
    const groups = loops(route(content, "tool"))[0]!.groups
    expect(groups).toHaveLength(1)
    expect(groups[0]!.segments.map((s) => s.toolName)).toEqual([
      "search",
      "read_page",
    ])
  })

  it("resets the loop when prose interrupts a run of tools", () => {
    const content = res("1", "X") + "\n\nSome prose here.\n\n" + res("2", "X")
    const blocks = route(content, "tool")
    expect(blocks.map((b) => b.type)).toEqual([
      "tool_loop",
      "content",
      "tool_loop",
    ])
  })

  it("parses per-call label, value_preview, value and error status", () => {
    const content = res(
      "1",
      "run_sql",
      'label="glucose" value-preview="1,204 rows" value="ok" value-type="text" status="error"',
    )
    const call = loops(route(content))[0]!.groups[0]!.calls[0]!
    // status attr on res() helper defaults success but our extra overrides it
    expect(call.label).toBe("glucose")
    expect(call.valuePreview).toBe("1,204 rows")
    expect(call.value).toBe("ok")
    expect(call.status).toBe("error")
  })

  it("pairs a request's arguments onto the result within one content string", () => {
    const content =
      req("1", "weather", 'arguments="{&quot;lat&quot;:45.5}"') +
      res("1", "weather", 'tool-title="Weather Forecast for Portland"')
    const call = loops(route(content))[0]!.groups[0]!.calls[0]!
    expect(call.arguments).toBe('{"lat":45.5}')
    expect(call.title).toBe("Weather Forecast for Portland")
  })

  it("parses attribute values containing '>' inside quotes (e.g. an icon)", () => {
    const icon =
      "&lt;svg&gt;&lt;path d=&quot;M0 0&gt;L1 1&quot;/&gt;&lt;/svg&gt;"
    const content = res("1", "list_files", `icon="${icon}"`)
    const l = loops(route(content))
    expect(l).toHaveLength(1)
    expect(l[0]!.groups[0]!.icon).toContain("<svg>")
    expect(l[0]!.groups[0]!.icon).toContain('d="M0 0>L1 1"')
  })

  it("preserves surrounding prose as content blocks", () => {
    const content = "Before. " + res("1", "X") + " After."
    const types = route(content).map((b) => b.type)
    expect(types).toEqual(["content", "tool_loop", "content"])
  })

  it("is a pure function of content — same input, deep-equal blocks (replay gate)", () => {
    const content =
      "intro\n\n" +
      req("1", "X", 'tool-title="Running X"') +
      res("1", "X", 'tool-title="Ran X"') +
      res("2", "Y") +
      "\n\noutro"
    const a = route(content, "tool")
    const b = route(content, "tool")
    expect(a).toEqual(b)
  })

  it("leaves a trailing incomplete tool element as prose (streaming safety)", () => {
    const content = res("1", "X") + '<shiny-tool-request request-id="2" tool-'
    const blocks = route(content)
    expect(loops(blocks)).toHaveLength(1)
    const tail = blocks[blocks.length - 1]!
    expect(tail.type).toBe("content")
  })

  it("merges adjacent tool loops that share a content type into one loop", () => {
    const input: MessageBlock[] = [
      { type: "content", content: res("1", "X"), contentType: "markdown" },
      { type: "content", content: res("2", "X"), contentType: "markdown" },
    ]
    const blocks = routeToolBlocks(input, "tool", "assistant")
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop"])
    const calls = (blocks[0] as ToolLoopBlock).groups.flatMap((g) => g.calls)
    expect(calls).toHaveLength(2)
  })

  it("does NOT merge adjacent tool loops from segments with different content types", () => {
    const input: MessageBlock[] = [
      { type: "content", content: res("1", "X"), contentType: "markdown" },
      { type: "content", content: res("2", "X"), contentType: "html" },
    ]
    const blocks = routeToolBlocks(input, "tool", "assistant")
    expect(blocks.map((b) => b.type)).toEqual(["tool_loop", "tool_loop"])
    expect((blocks[0] as ToolLoopBlock).contentType).toBe("markdown")
    expect((blocks[1] as ToolLoopBlock).contentType).toBe("html")
    // Each loop keeps only its own call, rather than the two being combined.
    expect(
      (blocks[0] as ToolLoopBlock).groups.flatMap((g) => g.calls),
    ).toHaveLength(1)
    expect(
      (blocks[1] as ToolLoopBlock).groups.flatMap((g) => g.calls),
    ).toHaveLength(1)
  })

  describe("role gate", () => {
    const typed = `${req("1", "search")}${res("1", "search")}`
    const userBlocks: MessageBlock[] = [
      { type: "content", content: typed, contentType: "markdown" },
    ]

    it("does not route tool elements a user typed", () => {
      const out = routeToolBlocks(userBlocks, "tool", "user")
      expect(out).toEqual(userBlocks)
      expect(loops(out)).toHaveLength(0)
      expect(contentFromBlocks(out)).toBe(typed)
    })

    it("still routes the same content in an assistant message", () => {
      const out = routeToolBlocks(userBlocks, "tool", "assistant")
      expect(loops(out)).toHaveLength(1)
    })

    it('still routes the same content in a "system" message', () => {
      // The client model names only "user" | "assistant", but Python's
      // server-side Role is Literal["assistant", "user", "system"], so a
      // system role really does arrive here. This pins the gate to
      // `role !== "user"` so it can't be narrowed to `role === "assistant"`.
      const out = routeToolBlocks(userBlocks, "tool", "system")
      expect(loops(out)).toHaveLength(1)
    })
  })

  describe("content-type allow-list", () => {
    const markup = `${req("1", "search")}${res("1", "search")}`
    const blocksOfType = (contentType: ContentType): MessageBlock[] => [
      { type: "content", content: markup, contentType },
    ]

    it('does not route a "text"-typed block', () => {
      // "text" means "display literally", so tool markup in it is a sample.
      const input = blocksOfType("text")
      const out = routeToolBlocks(input, "tool", "assistant")
      expect(out).toEqual(input)
      expect(loops(out)).toHaveLength(0)
    })

    it.each(["markdown", "html"] as const)(
      'still routes a "%s"-typed block',
      (contentType) => {
        const out = routeToolBlocks(
          blocksOfType(contentType),
          "tool",
          "assistant",
        )
        expect(loops(out)).toHaveLength(1)
      },
    )
  })
})

describe("toolGrouping state wiring (Phase 1)", () => {
  function res(id: string, name: string): string {
    return `<shiny-tool-result data-shinychat-react request-id="${id}" tool-name="${name}" status="success"></shiny-tool-result>`
  }
  const twoTools = res("1", "X") + res("2", "Y")

  function loopGroups(msg: ChatMessageData) {
    const loop = msg.blocks.find((b) => b.type === "tool_loop") as
      | ToolLoopBlock
      | undefined
    return loop?.groups ?? []
  }

  it('defaults toolGrouping to "tool"', () => {
    expect(initialState.toolGrouping).toBe("tool")
  })

  it("routes a dispatched message with the state's toolGrouping (all)", () => {
    const state = makeState({ toolGrouping: "all" })
    const next = chatReducer(state, {
      type: "message",
      message: {
        role: "assistant",
        segments: [{ content: twoTools, content_type: "markdown" }],
      },
    })
    const groups = loopGroups(next.messages[0]!)
    expect(groups).toHaveLength(1)
    expect(groups[0]!.count).toBe(2)
  })

  it('groups by tool name when toolGrouping is "tool"', () => {
    const state = makeState({ toolGrouping: "tool" })
    const next = chatReducer(state, {
      type: "message",
      message: {
        role: "assistant",
        segments: [{ content: twoTools, content_type: "markdown" }],
      },
    })
    const groups = loopGroups(next.messages[0]!)
    expect(groups.map((g) => g.toolName)).toEqual(["X", "Y"])
  })

  it("preserves toolGrouping across a clear", () => {
    const state = makeState({ toolGrouping: "all" })
    const next = chatReducer(state, { type: "clear" })
    expect(next.toolGrouping).toBe("all")
  })
})
