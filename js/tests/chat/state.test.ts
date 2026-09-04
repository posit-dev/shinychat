import { describe, it, expect, vi, beforeEach } from "vitest"
import {
  chatReducer,
  contentFromBlocks,
  initialState,
  structuredBlockToLoop,
  supersededRequestIds,
  type ChatState,
  type ChatMessageData,
  type GreetingData,
  type ChatDrawerState,
  type ToolLoopBlock,
  type ToolGrouping,
} from "../../src/chat/state"
import type {
  HtmlDep,
  ToolRequestBlock,
  ToolResultBlock,
} from "../../src/transport/types"
import { uuid } from "../../src/utils/uuid"

vi.mock("../../src/utils/uuid")

beforeEach(() => {
  let counter = 0
  vi.mocked(uuid).mockImplementation(() => `uuid-${++counter}`)
})

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...initialState, ...overrides }
}

function makeArtifact(
  overrides: Partial<ChatDrawerState> = {},
): ChatDrawerState {
  return { ...initialState.drawer, enabled: true, ...overrides }
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
        contentType: "markdown",
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

    it("preserves artifact state across clear", () => {
      const artifact = makeArtifact({
        visible: true,
        title: "Preview",
        content: "<p>Artifact</p>",
        htmlDeps: [{ name: "preview", version: "1.0.0" }],
      })
      const next = chatReducer(makeState({ drawer: artifact }), {
        type: "clear",
      })
      expect(next.drawer).toEqual(artifact)
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

    it("leaves an open streaming message untouched", () => {
      // The server may send remove_loading while a response is still
      // streaming (e.g. an R slash-command handler that starts an async
      // stream returns before it finishes). Finalizing here would truncate
      // the response, so the stream, the composer lock, and cancelRequested
      // are all left for chunk_end to resolve.
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        streamingMessage: msg,
        inputDisabled: true,
        cancelRequested: true,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.streamingMessage).toBe(msg)
      expect(next.messages).toHaveLength(0)
      expect(next.inputDisabled).toBe(true)
      expect(next.cancelRequested).toBe(true)
    })

    it("still removes the placeholder when a stream is open", () => {
      const placeholder: ChatMessageData = {
        id: "p",
        role: "assistant",
        content: "",
        streaming: false,
        isPlaceholder: true,
        blocks: [],
      }
      const msg = makeAssistantMsg({ streaming: true })
      const state = makeState({
        messages: [placeholder],
        streamingMessage: msg,
        inputDisabled: true,
      })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.messages).toHaveLength(0)
      expect(next.streamingMessage).toBe(msg)
    })

    it("resets cancelRequested even without a streaming message", () => {
      const state = makeState({ cancelRequested: true })
      const next = chatReducer(state, { type: "remove_loading" })
      expect(next.cancelRequested).toBe(false)
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
      expect(block.content).toContain("shiny-chat-thinking-topic")
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
      expect(block2.content).toContain("shiny-chat-thinking-topic")
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

    it("chunk_end finalizes in-flight thinking blocks", () => {
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
      const next = chatReducer(state, { type: "chunk_end" })
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
      const onlyBlock = msg.blocks[0]!
      if (onlyBlock.type !== "content")
        throw new Error("expected content block")
      expect(onlyBlock.content).toBe(content)
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

    it("does not reset artifact state", () => {
      const artifact = makeArtifact({
        visible: true,
        content: "<div>Retained</div>",
      })
      const next = chatReducer(makeState({ drawer: artifact }), {
        type: "history_update",
        enabled: true,
        conversations: [],
        active_id: null,
      })
      expect(next.drawer).toBe(artifact)
    })
  })

  describe("update_siblings", () => {
    it("sets siblings on the targeted message and leaves others untouched", () => {
      const msg0 = makeAssistantMsg({ id: "m0", role: "user", content: "q1" })
      const msg1 = makeAssistantMsg({ id: "m1", content: "a1" })
      const state = makeState({ messages: [msg0, msg1] })
      const next = chatReducer(state, {
        type: "update_siblings",
        data: { 0: { index: 1, total: 2 } },
      })
      expect(next.messages[0]!.siblings).toEqual({ index: 1, total: 2 })
      expect(next.messages[1]!.siblings).toBeUndefined()
      expect(next.messages[1]).toBe(state.messages[1])
    })

    it("clears siblings from a message no longer present in a sparse data map", () => {
      const msg0 = makeAssistantMsg({
        id: "m0",
        role: "user",
        content: "q1",
        siblings: { index: 1, total: 2 },
      })
      const msg1 = makeAssistantMsg({ id: "m1", content: "a1" })
      const state = makeState({ messages: [msg0, msg1] })
      const next = chatReducer(state, {
        type: "update_siblings",
        data: {},
      })
      expect(next.messages[0]!.siblings).toBeUndefined()
      expect(next.messages[1]!.siblings).toBeUndefined()
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

describe("supersededRequestIds", () => {
  const request = (id: string): ToolRequestBlock => ({
    type: "tool_request",
    version: 1,
    request_id: id,
    tool_name: "search",
    arguments: "{}",
  })
  const result = (id: string): ToolResultBlock => ({
    type: "tool_result",
    version: 1,
    request_id: id,
    tool_name: "search",
    status: "success",
    value: "ok",
    value_type: "text",
  })

  function routed(
    blocks: Array<ToolRequestBlock | ToolResultBlock>,
    overrides: Partial<ChatMessageData> = {},
  ): ChatMessageData {
    const loops = blocks
      .map((b) => structuredBlockToLoop(b, "tool"))
      .filter((l): l is ToolLoopBlock => l !== null)
    return {
      id: "m",
      role: "assistant",
      content: "",
      streaming: false,
      ...overrides,
      blocks: loops,
    }
  }

  function unrouted(
    blocks: Array<ToolRequestBlock | ToolResultBlock>,
    overrides: Partial<ChatMessageData> = {},
  ): ChatMessageData {
    const loops = blocks
      .map((b) => structuredBlockToLoop(b, "tool"))
      .filter((l): l is ToolLoopBlock => l !== null)
    return {
      id: "m",
      role: "assistant",
      content: "",
      streaming: true,
      ...overrides,
      blocks: loops,
    }
  }

  it("collects the id of a result paired in a finalized message", () => {
    const ids = supersededRequestIds(
      [routed([request("req-1"), result("req-1")])],
      null,
    )
    expect([...ids]).toEqual(["req-1"])
  })

  it("collects across messages, so a result supersedes a request in an earlier one", () => {
    const ids = supersededRequestIds(
      [routed([request("req-1")]), routed([result("req-1")])],
      null,
    )
    expect(ids.has("req-1")).toBe(true)
  })

  it("collects from the streaming message, whose blocks are not routed yet", () => {
    const ids = supersededRequestIds(
      [routed([request("req-1")])],
      unrouted([result("req-1")]),
    )
    expect(ids.has("req-1")).toBe(true)
  })

  it("omits a request that has no result — nothing supersedes it", () => {
    const ids = supersededRequestIds([routed([request("req-1")])], null)
    expect(ids.size).toBe(0)
  })

  it("ignores a result in a user message, which must not blank a real call", () => {
    const ids = supersededRequestIds(
      [
        routed([request("req-1")]),
        routed([result("req-1")], { id: "u", role: "user" }),
      ],
      null,
    )
    expect(ids.size).toBe(0)
  })

  it("never collects the empty id a block without request_id yields", () => {
    const bare: ToolResultBlock = {
      type: "tool_result",
      version: 1,
      request_id: "",
      tool_name: "search",
      status: "success",
      value: "ok",
      value_type: "text",
    }
    const ids = supersededRequestIds([routed([bare])], null)
    expect(ids.has("")).toBe(false)
    expect(ids.size).toBe(0)
  })
})

describe("toolGrouping state wiring (Phase 1)", () => {
  const result = (id: string, name: string): ToolResultBlock => ({
    type: "tool_result",
    version: 1,
    request_id: id,
    tool_name: name,
    status: "success",
  })
  const twoTools: ToolResultBlock[] = [result("1", "X"), result("2", "Y")]

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
        segments: twoTools,
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
        segments: twoTools,
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

  describe("SET_TOOL_GROUPING", () => {
    function stateWithTranscript(grouping: ToolGrouping): ChatState {
      return chatReducer(makeState({ toolGrouping: grouping }), {
        type: "message",
        message: {
          role: "assistant",
          segments: twoTools,
        },
      })
    }

    it("re-routes the settled transcript at the new mode", () => {
      const next = chatReducer(stateWithTranscript("tool"), {
        type: "SET_TOOL_GROUPING",
        grouping: "all",
      })
      expect(next.toolGrouping).toBe("all")
      const groups = loopGroups(next.messages[0]!)
      expect(groups).toHaveLength(1)
      expect(groups[0]!.count).toBe(2)
    })

    it("keeps message identity so nothing remounts", () => {
      const before = stateWithTranscript("tool")
      const after = chatReducer(before, {
        type: "SET_TOOL_GROUPING",
        grouping: "none",
      })
      expect(after.messages.map((m) => m.id)).toEqual(
        before.messages.map((m) => m.id),
      )
      expect(loopGroups(after.messages[0]!)).toHaveLength(2)
    })

    it("is a no-op for the mode already in effect", () => {
      const before = stateWithTranscript("all")
      const after = chatReducer(before, {
        type: "SET_TOOL_GROUPING",
        grouping: "all",
      })
      expect(after).toBe(before)
    })

    it("regroups the in-flight streaming message too", () => {
      let state = makeState({ toolGrouping: "tool" })
      state = chatReducer(state, {
        type: "chunk_start",
        message: { role: "assistant", segments: [] },
      })
      for (const block of twoTools) {
        state = chatReducer(state, { type: "block_insert", block })
      }
      expect(loopGroups(state.streamingMessage!)).toHaveLength(2)

      const next = chatReducer(state, {
        type: "SET_TOOL_GROUPING",
        grouping: "all",
      })

      const groups = loopGroups(next.streamingMessage!)
      expect(groups).toHaveLength(1)
      expect(groups[0]!.count).toBe(2)
    })

    it("leaves a message with no tool calls untouched", () => {
      const before = chatReducer(makeState({ toolGrouping: "tool" }), {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "just prose", content_type: "markdown" }],
        },
      })
      const after = chatReducer(before, {
        type: "SET_TOOL_GROUPING",
        grouping: "all",
      })
      expect(after.messages[0]).toBe(before.messages[0])
    })
  })
})

describe("html_deps retention", () => {
  const dep: HtmlDep = { name: "widget", version: "1.0.0" }

  it("attaches html_deps from a message action to the message", () => {
    const next = chatReducer(initialState, {
      type: "message",
      message: {
        role: "assistant",
        segments: [{ content: "hi", content_type: "markdown" }],
      },
      html_deps: [dep],
    })
    const last = next.messages[next.messages.length - 1]!
    expect(last.htmlDeps).toEqual([dep])
  })

  it("accumulates html_deps across streaming chunks", () => {
    let s = chatReducer(initialState, {
      type: "chunk_start",
      message: { role: "assistant", segments: [] },
      html_deps: [dep],
    })
    s = chatReducer(s, {
      type: "chunk",
      content: "x",
      operation: "append",
      content_type: "markdown",
    })
    s = chatReducer(s, { type: "chunk_end" })
    const last = s.messages[s.messages.length - 1]!
    expect(last.htmlDeps).toEqual([dep])
  })
})
