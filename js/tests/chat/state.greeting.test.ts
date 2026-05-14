import { describe, it, expect, vi, beforeEach } from "vitest"
import { chatReducer, initialState, type ChatState } from "../../src/chat/state"
import { uuid } from "../../src/utils/uuid"

vi.mock("../../src/utils/uuid")

beforeEach(() => {
  let counter = 0
  vi.mocked(uuid).mockImplementation(() => `uuid-${++counter}`)
})

function makeState(overrides: Partial<ChatState> = {}): ChatState {
  return { ...initialState, ...overrides }
}

describe("chatReducer — greeting actions", () => {
  describe("greeting", () => {
    it("sets greeting with visible:true, dismissed:false, streaming:false when no messages", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "greeting",
        content: "Hello!",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting).toMatchObject({
        content: "Hello!",
        contentType: "markdown",
        visible: true,
        dismissed: false,
        streaming: false,
      })
    })

    it("stores the correct block", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "greeting",
        content: "Hello!",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting?.blocks).toEqual([
        { type: "content", content: "Hello!", contentType: "markdown" },
      ])
    })

    it("auto-dismisses when dismissible:true and messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            contentType: "markdown",
            streaming: false,
            blocks: [],
          },
        ],
      })
      const next = chatReducer(state, {
        type: "greeting",
        content: "Hi there",
        content_type: "markdown",
        options: { dismissible: true },
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("auto-dismisses when options.dismissible is omitted (defaults to dismissible) and messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            contentType: "markdown",
            streaming: false,
            blocks: [],
          },
        ],
      })
      const next = chatReducer(state, {
        type: "greeting",
        content: "Hi",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("does not auto-dismiss when dismissible:false even if messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            contentType: "markdown",
            streaming: false,
            blocks: [],
          },
        ],
      })
      const next = chatReducer(state, {
        type: "greeting",
        content: "Sticky greeting",
        content_type: "markdown",
        options: { dismissible: false },
      })
      expect(next.greeting).toMatchObject({ visible: true, dismissed: false })
    })

    it("is a no-op when current greeting is already dismissed", () => {
      const state = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          visible: false,
          dismissed: true,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "greeting",
        content: "new",
        content_type: "markdown",
        options: {},
      })
      expect(next).toBe(state)
    })
  })

  describe("greeting_start", () => {
    it("sets greeting with streaming:true", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "greeting_start",
        content: "Streaming…",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting).toMatchObject({
        content: "Streaming…",
        streaming: true,
        visible: true,
        dismissed: false,
      })
    })

    it("auto-dismisses when dismissible and messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            contentType: "markdown",
            streaming: false,
            blocks: [],
          },
        ],
      })
      const next = chatReducer(state, {
        type: "greeting_start",
        content: "",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("is a no-op when current greeting is already dismissed", () => {
      const state = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          visible: false,
          dismissed: true,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "greeting_start",
        content: "new",
        content_type: "markdown",
        options: {},
      })
      expect(next).toBe(state)
    })

    it("creates an empty blocks array when content is empty string", () => {
      const state = makeState()
      const next = chatReducer(state, {
        type: "greeting_start",
        content: "",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting?.blocks).toEqual([])
    })
  })

  describe("greeting_chunk", () => {
    function makeStreamingGreeting(content = "Hello"): ChatState {
      return makeState({
        greeting: {
          content,
          contentType: "markdown",
          streaming: true,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [{ type: "content", content, contentType: "markdown" }],
        },
      })
    }

    it("appends content when operation is 'append'", () => {
      const state = makeStreamingGreeting("Hello")
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: " World",
        operation: "append",
      })
      expect(next.greeting?.content).toBe("Hello World")
      expect(next.greeting?.blocks).toEqual([
        { type: "content", content: "Hello World", contentType: "markdown" },
      ])
    })

    it("replaces content when operation is 'replace'", () => {
      const state = makeStreamingGreeting("old text")
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "new text",
        operation: "replace",
      })
      expect(next.greeting?.content).toBe("new text")
      expect(next.greeting?.blocks).toEqual([
        { type: "content", content: "new text", contentType: "markdown" },
      ])
    })

    it("creates a new block when content_type changes", () => {
      const state = makeStreamingGreeting("markdown text")
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "<b>html</b>",
        operation: "append",
        content_type: "html",
      })
      expect(next.greeting?.blocks).toHaveLength(2)
      expect(next.greeting?.blocks[0]).toEqual({
        type: "content",
        content: "markdown text",
        contentType: "markdown",
      })
      expect(next.greeting?.blocks[1]).toEqual({
        type: "content",
        content: "<b>html</b>",
        contentType: "html",
      })
    })

    it("is a no-op when greeting is null", () => {
      const state = makeState({ greeting: null })
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("is a no-op when greeting is dismissed", () => {
      const state = makeState({
        greeting: {
          content: "dismissed",
          contentType: "markdown",
          streaming: true,
          visible: false,
          dismissed: true,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })

    it("is a no-op when greeting is not streaming", () => {
      const state = makeState({
        greeting: {
          content: "final",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [
            { type: "content", content: "final", contentType: "markdown" },
          ],
        },
      })
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "x",
        operation: "append",
      })
      expect(next).toBe(state)
    })
  })

  describe("greeting_end", () => {
    it("sets streaming to false", () => {
      const state = makeState({
        greeting: {
          content: "done",
          contentType: "markdown",
          streaming: true,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [
            { type: "content", content: "done", contentType: "markdown" },
          ],
        },
      })
      const next = chatReducer(state, { type: "greeting_end" })
      expect(next.greeting?.streaming).toBe(false)
      expect(next.greeting?.content).toBe("done")
    })

    it("is a no-op when greeting is not streaming", () => {
      const state = makeState({
        greeting: {
          content: "done",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_end" })
      expect(next).toBe(state)
    })

    it("is a no-op when greeting is null", () => {
      const state = makeState({ greeting: null })
      const next = chatReducer(state, { type: "greeting_end" })
      expect(next).toBe(state)
    })
  })

  describe("greeting_clear", () => {
    it("sets greeting to null", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_clear" })
      expect(next.greeting).toBeNull()
    })

    it("allows a subsequent greeting action to set a new greeting after clear", () => {
      const dismissed = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          visible: false,
          dismissed: true,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const cleared = chatReducer(dismissed, { type: "greeting_clear" })
      expect(cleared.greeting).toBeNull()

      const renewed = chatReducer(cleared, {
        type: "greeting",
        content: "new",
        content_type: "markdown",
        options: {},
      })
      expect(renewed.greeting).toMatchObject({
        content: "new",
        visible: true,
        dismissed: false,
      })
    })
  })

  describe("INPUT_SENT dismisses greeting", () => {
    it("dismisses a dismissible visible greeting on user input", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: { dismissible: true },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("does not dismiss a non-dismissible greeting on user input", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
      expect(next.greeting).toMatchObject({ visible: true, dismissed: false })
    })
  })

  describe("message dismisses greeting", () => {
    it("dismisses a dismissible visible greeting when a message arrives", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply",
          content_type: "markdown",
        },
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("does not dismiss a non-dismissible greeting when a message arrives", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          content: "Reply",
          content_type: "markdown",
        },
      })
      expect(next.greeting).toMatchObject({ visible: true, dismissed: false })
    })
  })

  describe("chunk_start dismisses greeting", () => {
    it("dismisses a dismissible visible greeting when streaming starts", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "...",
          content_type: "markdown",
        },
      })
      expect(next.greeting).toMatchObject({ visible: false, dismissed: true })
    })

    it("does not dismiss a non-dismissible greeting when streaming starts", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: true,
          dismissed: false,
          dismissing: false,
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          content: "...",
          content_type: "markdown",
        },
      })
      expect(next.greeting).toMatchObject({ visible: true, dismissed: false })
    })
  })

  describe("clear re-shows greeting", () => {
    it("restores a dismissed greeting to visible:true, dismissed:false", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          visible: false,
          dismissed: true,
          dismissing: false,
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.greeting).toMatchObject({ visible: true, dismissed: false })
    })

    it("preserves null greeting after clear when no greeting was set", () => {
      const state = makeState({ greeting: null })
      const next = chatReducer(state, { type: "clear" })
      expect(next.greeting).toBeNull()
    })
  })
})
