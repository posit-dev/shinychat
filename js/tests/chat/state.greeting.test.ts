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
    it("sets greeting with status:visible, streaming:false when no messages", () => {
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
        status: "visible",
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
      expect(next.greeting).toMatchObject({ status: "dismissed" })
    })

    it("auto-dismisses when options.dismissible is omitted (defaults to dismissible) and messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
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
      expect(next.greeting).toMatchObject({ status: "dismissed" })
    })

    it("does not auto-dismiss when dismissible:false even if messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
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
      expect(next.greeting).toMatchObject({ status: "visible" })
    })

    it("updates content while preserving dismissed state", () => {
      const state = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
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
      expect(next.greeting).toMatchObject({
        content: "new",
        status: "dismissed",
      })
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
        status: "visible",
      })
    })

    it("auto-dismisses when dismissible and messages exist", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
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
      expect(next.greeting).toMatchObject({ status: "dismissed" })
    })

    it("updates streaming greeting while preserving dismissed state", () => {
      const state = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
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
      expect(next.greeting).toMatchObject({
        content: "new",
        streaming: true,
        status: "dismissed",
      })
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
          status: "visible",
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

    it("buffers chunks into a dismissed but streaming greeting", () => {
      const state = makeState({
        greeting: {
          content: "",
          contentType: "markdown",
          streaming: true,
          status: "dismissed",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "greeting_chunk",
        content: "hidden update",
        operation: "append",
      })
      expect(next.greeting).toMatchObject({
        content: "hidden update",
        status: "dismissed",
      })
    })

    it("is a no-op when greeting is not streaming", () => {
      const state = makeState({
        greeting: {
          content: "final",
          contentType: "markdown",
          streaming: false,
          status: "visible",
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
          status: "visible",
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

    it("clears greeting when stream produced no content", () => {
      const state = makeState({
        greeting: {
          content: "",
          contentType: "markdown",
          streaming: true,
          status: "visible",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_end" })
      expect(next.greeting).toBeNull()
    })

    it("is a no-op when greeting is not streaming", () => {
      const state = makeState({
        greeting: {
          content: "done",
          contentType: "markdown",
          streaming: false,
          status: "visible",
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
          status: "visible",
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
          status: "dismissed",
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
        status: "visible",
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
          status: "visible",
          options: { dismissible: true },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
      expect(next.greeting).toMatchObject({ status: "dismissing" })
    })

    it("does not dismiss a non-dismissible greeting on user input", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
      expect(next.greeting).toMatchObject({ status: "visible" })
    })
  })

  describe("message dismisses greeting", () => {
    it("dismisses a dismissible visible greeting when a message arrives", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Reply", content_type: "markdown" }],
        },
      })
      expect(next.greeting).toMatchObject({ status: "dismissing" })
    })

    it("does not dismiss a non-dismissible greeting when a message arrives", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "message",
        message: {
          role: "assistant",
          segments: [{ content: "Reply", content_type: "markdown" }],
        },
      })
      expect(next.greeting).toMatchObject({ status: "visible" })
    })
  })

  describe("chunk_start dismisses greeting", () => {
    it("dismisses a dismissible visible greeting when streaming starts", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "...", content_type: "markdown" }],
        },
      })
      expect(next.greeting).toMatchObject({ status: "dismissing" })
    })

    it("does not dismiss a non-dismissible greeting when streaming starts", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: { dismissible: false },
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "chunk_start",
        message: {
          role: "assistant",
          segments: [{ content: "...", content_type: "markdown" }],
        },
      })
      expect(next.greeting).toMatchObject({ status: "visible" })
    })
  })

  describe("clear re-shows greeting", () => {
    it("restores a dismissed greeting to status:visible", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.greeting).toMatchObject({ status: "visible" })
    })

    it("preserves null greeting after clear when no greeting was set", () => {
      const state = makeState({ greeting: null })
      const next = chatReducer(state, { type: "clear" })
      expect(next.greeting).toBeNull()
    })

    it("surfaces an updated-while-dismissed greeting after clear", () => {
      // Start with an initial visible greeting
      let state = makeState()
      state = chatReducer(state, {
        type: "greeting",
        content: "original",
        content_type: "markdown",
        options: {},
      })
      // User dismisses it via INPUT_SENT
      state = chatReducer(state, {
        type: "INPUT_SENT",
        content: "hi",
        role: "user",
      })
      expect(state.greeting).toMatchObject({
        status: "dismissing",
      })
      // Server updates the greeting while dismissed
      state = chatReducer(state, {
        type: "greeting",
        content: "refreshed",
        content_type: "markdown",
        options: {},
      })
      expect(state.greeting).toMatchObject({
        content: "refreshed",
        status: "dismissed",
      })
      // User clears the chat → updated greeting re-appears
      state = chatReducer(state, { type: "clear" })
      expect(state.greeting).toMatchObject({
        content: "refreshed",
        status: "visible",
      })
    })
  })

  describe("greeting_dismissed", () => {
    it("transitions dismissing to dismissed", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "dismissing",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_dismissed" })
      expect(next.greeting).toMatchObject({ status: "dismissed" })
    })

    it("is a no-op when greeting is null", () => {
      const state = makeState({ greeting: null })
      const next = chatReducer(state, { type: "greeting_dismissed" })
      expect(next).toBe(state)
    })

    it("is a no-op when status is visible (not dismissing)", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_dismissed" })
      expect(next).toBe(state)
    })

    it("is a no-op when status is already dismissed", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "greeting_dismissed" })
      expect(next).toBe(state)
    })
  })

  describe("greeting replacement during dismissing animation", () => {
    it("accepts new greeting content while status is dismissing (with messages)", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            streaming: false,
            blocks: [],
          },
        ],
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          status: "dismissing",
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
      expect(next.greeting).toMatchObject({
        content: "new",
        status: "dismissed",
      })
    })

    it("accepts greeting_start while status is dismissing (with messages)", () => {
      const state = makeState({
        messages: [
          {
            id: "m1",
            role: "user",
            content: "hi",
            streaming: false,
            blocks: [],
          },
        ],
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          status: "dismissing",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, {
        type: "greeting_start",
        content: "",
        content_type: "markdown",
        options: {},
      })
      expect(next.greeting).toMatchObject({
        streaming: true,
        status: "dismissed",
      })
    })

    it("replaces greeting as visible when dismissing with no messages (edge case)", () => {
      const state = makeState({
        greeting: {
          content: "old",
          contentType: "markdown",
          streaming: false,
          status: "dismissing",
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
      expect(next.greeting).toMatchObject({
        content: "new",
        status: "visible",
      })
    })
  })

  describe("clear with greeting flag", () => {
    it("sets greeting to null when action.greeting is true", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "visible",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "clear", greeting: true })
      expect(next.greeting).toBeNull()
      expect(next.messages).toEqual([])
    })

    it("clears a dismissed greeting when action.greeting is true", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "clear", greeting: true })
      expect(next.greeting).toBeNull()
    })

    it("re-shows greeting when action.greeting is falsy", () => {
      const state = makeState({
        greeting: {
          content: "Hello",
          contentType: "markdown",
          streaming: false,
          status: "dismissed",
          options: {},
          blocks: [],
        },
      })
      const next = chatReducer(state, { type: "clear" })
      expect(next.greeting).toMatchObject({ status: "visible" })
    })
  })
})
